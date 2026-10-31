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

# Application source allowlist; secrets and runtime state stay outside the image.
COPY --chown=app:app contracts/*.py contracts/*.sql ./contracts/
COPY --chown=app:app logistics_an_nguyen/*.py ./logistics_an_nguyen/
COPY --chown=app:app logistics_an_nguyen/ui/index.html logistics_an_nguyen/ui/app.js logistics_an_nguyen/ui/data.mjs logistics_an_nguyen/ui/styles.css ./logistics_an_nguyen/ui/
COPY --chown=app:app care_truc/*.py care_truc/schema.sql ./care_truc/
COPY --chown=app:app platform_huy/*.py ./platform_huy/
COPY --chown=app:app platform_huy/migrations/*.sql ./platform_huy/migrations/
COPY --chown=app:app platform_huy/ui_prototype/ ./platform_huy/ui_prototype/
COPY --chown=app:app deploy/*.py ./deploy/

# Embed only the approved immutable release pair; HF remains a startup fallback.
COPY --chown=app:app data/release_main/core_14d.sqlite data/release_main/ops_14d.sqlite ${SEA_RELEASE_DIR}/
RUN chmod 0444 "${SEA_RELEASE_DIR}/core_14d.sqlite" "${SEA_RELEASE_DIR}/ops_14d.sqlite"

EXPOSE 7860
CMD ["python", "-m", "deploy.start_space"]
