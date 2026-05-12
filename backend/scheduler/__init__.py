from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from backend.core.database import get_session_local
from backend.models.task import Task
from backend.services.tasks import run_task_once

scheduler: AsyncIOScheduler | None = None
logger = logging.getLogger("backend.scheduler")


def create_cron_trigger(cron_str: str) -> CronTrigger:
    """自动解析格式并创建 CronTrigger，支持 5位和6位 cron 表达式以及 HH:MM 或 HH:MM:SS"""
    if ":" in cron_str:
        parts = cron_str.split(":")
        try:
            if len(parts) == 2:
                hour, minute = parts
                cron_str = f"0 {int(minute)} {int(hour)} * * *"
            elif len(parts) == 3:
                hour, minute, second = parts
                cron_str = f"{int(second)} {int(minute)} {int(hour)} * * *"
        except ValueError:
            pass

    parts = cron_str.split()
    if len(parts) == 6:
        return CronTrigger(
            second=parts[0],
            minute=parts[1],
            hour=parts[2],
            day=parts[3],
            month=parts[4],
            day_of_week=parts[5]
        )
    return CronTrigger.from_crontab(cron_str)


async def _job_run_task(task_id: int) -> None:
    db: Session = get_session_local()()
    try:
        # 这里的查询是同步的，对于 SQLite 且任务量不大可以接受
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task or not task.enabled:
            return
        # run_task_once 将被改为 async
        await run_task_once(db, task)
    finally:
        db.close()


async def _job_run_sign_task(account_name: str, task_name: str) -> None:
    """运行签到任务的 Job 包装器"""
    import asyncio
    import random
    from datetime import datetime, timedelta

    from backend.services.sign_tasks import get_sign_task_service

    try:
        logger.info("开始执行签到任务 %s (账号: %s)", task_name, account_name)

        # 获取任务配置，检查是否为随机时间段模式
        sign_task_service = get_sign_task_service()
        task_config = sign_task_service.get_task(task_name, account_name)
        if task_config and task_config.get("execution_mode") == "range":
            range_start_str = task_config.get("range_start")
            range_end_str = task_config.get("range_end")

            if range_start_str and range_end_str:
                try:
                    # 解析时间
                    fmt = "%H:%M"
                    start_time = datetime.strptime(range_start_str, fmt).time()
                    end_time = datetime.strptime(range_end_str, fmt).time()

                    # 转换为当前日期的 datetime
                    now = datetime.now()
                    start_dt = now.replace(
                        hour=start_time.hour,
                        minute=start_time.minute,
                        second=0,
                        microsecond=0,
                    )
                    end_dt = now.replace(
                        hour=end_time.hour,
                        minute=end_time.minute,
                        second=0,
                        microsecond=0,
                    )

                    # 如果结束时间小于开始时间，假设是第二天（虽然CRON触发通常在开始时间，这里做个防御）
                    if end_dt < start_dt:
                        end_dt += timedelta(days=1)

                    # 计算总秒数
                    total_seconds = (end_dt - start_dt).total_seconds()

                    if total_seconds > 0:
                        delay_seconds = random.uniform(0, total_seconds)
                        logger.info(
                            "任务 %s 随机时间段模式 (%s - %s)，等待 %ds (%.1f 分钟) 后执行",
                            task_name, range_start_str, range_end_str,
                            int(delay_seconds), delay_seconds / 60,
                        )
                        await asyncio.sleep(delay_seconds)

                except Exception as e:
                    logger.error("计算随机时间段延迟失败: %s — 立即执行任务 %s", e, task_name)

        sign_task_service = get_sign_task_service()
        result = await sign_task_service.run_task_with_logs(account_name, task_name)
        if result.get("success"):
            logger.info("任务 %s 执行成功", task_name)
        else:
            logger.error("任务 %s 执行失败: %s", task_name, result.get("error"))
    except Exception as e:
        logger.error("运行签到任务 %s 异常: %s", task_name, e, exc_info=True)


async def _job_maintenance() -> None:
    """每日维护任务：清理旧日志等"""
    db: Session = get_session_local()()
    try:
        from backend.services.sign_tasks import get_sign_task_service
        from backend.services.tasks import cleanup_old_logs

        count = cleanup_old_logs(db, days=3)
        logger.info("Maintenance: 已清理 %d 条数据库任务日志", count)
        get_sign_task_service()._cleanup_old_logs()
    finally:
        db.close()


def _schedule_range_catchup(account_name: str, task_name: str, st: dict) -> None:
    """
    如果当前时刻处于 range 窗口内且今日尚未执行，添加一次性立即任务。
    用于解决"窗口已开始后才创建/启动任务，当天不执行"的问题。
    """
    global scheduler
    if not scheduler:
        return

    import random
    from datetime import datetime, timedelta

    from apscheduler.triggers.date import DateTrigger

    range_start_str = st.get("range_start", "")
    range_end_str = st.get("range_end", "")
    if not range_start_str or not range_end_str:
        return

    try:
        fmt = "%H:%M"
        now = datetime.now()
        start_t = datetime.strptime(range_start_str, fmt).time()
        end_t = datetime.strptime(range_end_str, fmt).time()

        start_dt = now.replace(hour=start_t.hour, minute=start_t.minute, second=0, microsecond=0)
        end_dt = now.replace(hour=end_t.hour, minute=end_t.minute, second=0, microsecond=0)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        if not (start_dt <= now <= end_dt):
            return  # 当前不在窗口内

        # 今日是否已执行过
        last_run = st.get("last_run")
        if isinstance(last_run, dict):
            try:
                last_dt = datetime.fromisoformat(last_run.get("time", ""))
                if last_dt.date() == now.date():
                    logger.debug("任务 %s 今日已执行，跳过窗口补执行", task_name)
                    return
            except Exception:
                pass

        remaining = (end_dt - now).total_seconds()
        if remaining <= 0:
            return

        delay = random.uniform(0, remaining)
        run_at = now + timedelta(seconds=delay)
        catchup_id = f"sign-{account_name}-{task_name}-catchup"

        scheduler.add_job(
            _job_run_sign_task,
            trigger=DateTrigger(run_date=run_at),
            id=catchup_id,
            args=[account_name, task_name],
            replace_existing=True,
        )
        logger.info(
            "任务 %s 处于时间窗口 (%s-%s)，将在 %d 秒后执行",
            task_name, range_start_str, range_end_str, int(delay),
        )
    except Exception as e:
        logger.warning("计划窗口补执行任务 %s 失败: %s", task_name, e)


async def sync_jobs() -> None:
    """
    Sync APScheduler jobs from DB tasks table and file-based sign tasks.
    """
    if scheduler is None:
        return

    from backend.services.sign_tasks import get_sign_task_service

    db: Session = get_session_local()()
    try:
        # 1. 同步数据库任务
        tasks = db.query(Task).filter(Task.enabled).all()
        existing_ids = {
            job.id
            for job in scheduler.get_jobs()
            if job.id.startswith("db-") or job.id.startswith("sign-")
        }
        desired_ids = set()

        for task in tasks:
            job_id = f"db-{task.id}"
            desired_ids.add(job_id)

            try:
                trigger = create_cron_trigger(task.cron)
                if job_id in existing_ids:
                    scheduler.reschedule_job(job_id, trigger=trigger)
                else:
                    scheduler.add_job(
                        _job_run_task,
                        trigger=trigger,
                        id=job_id,
                        args=[task.id],
                        replace_existing=True,
                    )
            except Exception as e:
                logger.error("Error scheduling DB task %s: %s", task.id, e)

        # 2. 同步签到任务 (SignTask)
        # 使用缓存的任务列表，减少 I/O
        sign_task_service = get_sign_task_service()
        sign_tasks = sign_task_service.list_tasks(force_refresh=False)
        for st in sign_tasks:
            account_name = str(st.get("account_name") or "").strip()
            task_name = str(st.get("name") or "").strip()
            if not account_name or not task_name:
                logger.warning("Skip scheduling sign task with missing account/name: %s", st)
                continue

            job_id = f"sign-{account_name}-{task_name}"
            desired_ids.add(job_id)

            # SignTask 目前默认都是启用的，或者根据 st['enabled']
            if not st.get("enabled", True):
                if job_id in existing_ids:
                    scheduler.remove_job(job_id)
                continue

            try:
                trigger = create_cron_trigger(st["sign_at"])
                if st.get("execution_mode") == "range" and st.get("range_start"):
                    trigger = create_cron_trigger(st["range_start"])

                if job_id in existing_ids:
                    scheduler.reschedule_job(job_id, trigger=trigger)
                else:
                    scheduler.add_job(
                        _job_run_sign_task,
                        trigger=trigger,
                        id=job_id,
                        args=[account_name, task_name],
                        replace_existing=True,
                    )

                # 若 range 模式且当前处于窗口内、今日未执行，补一次立即执行
                if st.get("execution_mode") == "range":
                    _schedule_range_catchup(account_name, task_name, st)
            except Exception as e:
                logger.error("Error scheduling sign task %s: %s", task_name, e)

        # remove obsolete jobs
        for job_id in existing_ids - desired_ids:
            scheduler.remove_job(job_id)
    finally:
        db.close()


async def init_scheduler(sync_on_startup: bool = True) -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        from backend.core.config import get_settings

        settings = get_settings()
        scheduler = AsyncIOScheduler(
            timezone=settings.timezone,
            job_defaults={
                "misfire_grace_time": 3600,  # 允许任务延迟 1 小时执行
                "coalesce": True,  # 合并积压的执行
                "max_instances": 10,  # 增加并发实例数，避免多账号任务相互阻塞
            },
        )
        scheduler.start()

        # 添加每日凌晨 3 点执行的维护任务
        scheduler.add_job(
            _job_maintenance,
            trigger=CronTrigger.from_crontab("0 3 * * *"),
            id="system-maintenance",
            replace_existing=True,
        )

        if sync_on_startup:
            await sync_jobs()
    return scheduler


def shutdown_scheduler() -> None:
    global scheduler
    if scheduler:
        scheduler.shutdown(wait=False)
        scheduler = None


def add_or_update_sign_task_job(
    account_name: str, task_name: str, cron_expression: str, enabled: bool = True
) -> None:
    """动态添加或更新签到任务 Job"""
    global scheduler
    if not scheduler:
        return

    job_id = f"sign-{account_name}-{task_name}"

    if not enabled:
        remove_sign_task_job(account_name, task_name)
        return

    try:
        cron = cron_expression
        trigger = create_cron_trigger(cron)

        # 总是使用 replace_existing=True 来覆盖旧的
        scheduler.add_job(
            _job_run_sign_task,
            trigger=trigger,
            id=job_id,
            args=[account_name, task_name],
            replace_existing=True,
        )
        logger.info("已添加/更新任务 %s -> %s", job_id, cron)
    except Exception as e:
        logger.error("添加任务 %s 失败: %s", job_id, e)


def remove_sign_task_job(account_name: str, task_name: str) -> None:
    """动态移除签到任务 Job"""
    global scheduler
    if not scheduler:
        return

    job_id = f"sign-{account_name}-{task_name}"
    try:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
            logger.info("已移除任务 %s", job_id)
    except Exception as e:
        logger.error("移除任务 %s 失败: %s", job_id, e)
