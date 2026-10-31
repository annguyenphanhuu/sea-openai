FROM python:3.11-slim

RUN useradd --create-home --uid 1000 app
USER app
WORKDIR /home/app/app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SEA_RELEASE_DIR=/home/app/app/data/release_main \
    SEA_STATE_PATH=/home/app/app/runs/integrated-demo/state.sqlite \
    SEA_INTEGRATED=1 \
    HF_HUB_DISABLE_PROGRESS_BARS=1

COPY --chown=app:app deploy/requirements.txt ./deploy/requirements.txt
RUN python -m pip install --user -r deploy/requirements.txt

# Source allowlist only. Never copy repository data, secrets or runtime state.
COPY --chown=app:app contracts/*.py contracts/*.sql ./contracts/
COPY --chown=app:app logistics_an_nguyen/*.py ./logistics_an_nguyen/
COPY --chown=app:app care_truc/*.py care_truc/schema.sql ./care_truc/
COPY --chown=app:app platform_huy/*.py ./platform_huy/
COPY --chown=app:app platform_huy/migrations/*.sql ./platform_huy/migrations/
COPY --chown=app:app platform_huy/ui_prototype/ ./platform_huy/ui_prototype/
COPY --chown=app:app deploy/*.py ./deploy/

EXPOSE 7860
CMD ["python", "-m", "deploy.start_space"]
