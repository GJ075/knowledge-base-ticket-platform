import asyncio

from app.services.eval_runner import run_evaluation
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, name="run_evaluation")
def run_evaluation_task(self, run_id: str) -> None:
    asyncio.run(run_evaluation(run_id))
