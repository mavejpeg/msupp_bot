from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from datetime import datetime
from database import get_pending_posts, async_session, ScheduledPost
from services.publisher import publish_scheduled
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

async def restore_scheduled_posts():
    posts = await get_pending_posts()
    for post in posts:
        if post.scheduled_at > datetime.now():
            scheduler.add_job(
                publish_scheduled,
                trigger=DateTrigger(run_date=post.scheduled_at),
                args=[post.id],
                id=f"post_{post.id}",
                replace_existing=True
            )
    logger.info(f"Restored {len(posts)} scheduled posts")

async def add_scheduled_job(post_id: int, run_date: datetime):
    scheduler.add_job(
        publish_scheduled,
        trigger=DateTrigger(run_date=run_date),
        args=[post_id],
        id=f"post_{post_id}"
    )

async def remove_scheduled_job(post_id: int):
    job_id = f"post_{post_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

async def reschedule_job(post_id: int, new_run_date: datetime):
    job_id = f"post_{post_id}"
    if scheduler.get_job(job_id):
        scheduler.reschedule_job(job_id, trigger=DateTrigger(run_date=new_run_date))