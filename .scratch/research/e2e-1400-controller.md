# Integrated HTTP/thread boundary research

Read existing CareRuntime/CareHarness/EffectDispatcher/MemoryStore and platform executor code before implementation. Care SQLite and asyncio locks require one event-loop thread; using asyncio.run for each HTTP request would move connection ownership and lose task lifecycle.

Official Python3.11 references checked:
- https://docs.python.org/3.11/library/asyncio-task.html — run_coroutine_threadsafe submits work from another OS thread and exposes a concurrent future.
- https://docs.python.org/3.11/library/asyncio-dev.html — most asyncio objects are not thread safe; route cross-thread calls through the loop.
- https://docs.python.org/3.11/library/http.server.html — ThreadingHTTPServer creates handler threads; retain existing local demo server and bind application work to the coordinator loop.

Decision: dedicated async coordinator owns bothruntime connections; synchronousHTTP handlers submit bounded calls, close shuts downownedtasks/connections. Keep existingA3-only factory mode for existingtests andexplicitintegratedflag for newdemo. No newwebframework ormodeldependency. Datafault/FM review remains actualoperatorinput; no hidden defaultclearance.

## HF deployment evidence

Official reference: https://huggingface.co/docs/huggingface_hub/main/guides/manage-spaces
Use create_repo(private=True, repo_type=space, space_sdk=docker), add_space_secret and add_space_variable. fetch_space_logs provides build/runtime logs. Tokens remain process memory; no CLI login credential file is created.

Actual account huythi121022 authenticated with authorized .env HR_TOKEN mapped only in memory to HF_TOKEN. The four approved release files were uploaded to private dataset huythi121022/sea-openai-release-main, commit425775f53e4200589a61139922f2ab21b8ff4445. HF adds its own .gitattributes; no truth or heldout files were uploaded.

Space creation returned402: Docker/Gradio hosting on free cpu-basic requires PRO. No paid hardware or subscription was purchased. No build exists yet, so zero Docker build attempts have occurred. User was notified; dataset and local UI remain available.

User explicitly authorized generating LIVE_PRESENTER_KEY and adding it to ignored .env. No secret value is recorded in research, logs or source. The private Space has not yet been created, so remote secret configuration remains pending.
