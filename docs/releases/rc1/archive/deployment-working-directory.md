# RC1 Deployment Working-Directory Root Cause

## Exact failing context

The failed candidate release was:

```text
/opt/project-field-mouse/releases/20260730T195150Z-source
```

The deployer inherited its launch directory instead of entering that release:

```text
pwd=/home/amcowden97
PWD=/home/amcowden97
PYTHONPATH=<unset>
sys.executable=/opt/project-field-mouse/releases/20260730T195150Z-source/.venv/bin/python
sys.prefix=/opt/project-field-mouse/releases/20260730T195150Z-source/.venv
sys.path=[
  "",
  "/usr/lib/python313.zip",
  "/usr/lib/python3.13",
  "/usr/lib/python3.13/lib-dynload",
  "/opt/project-field-mouse/releases/20260730T195150Z-source/.venv/lib/python3.13/site-packages"
]
```

Because the empty `sys.path` entry represented `/home/amcowden97`, this
command reproduced the deployment failure:

```text
/opt/project-field-mouse/releases/20260730T195150Z-source/.venv/bin/python \
  -c 'import app'
ModuleNotFoundError: No module named 'app'
```

## Release layout

The candidate was complete. These files existed:

```text
/opt/project-field-mouse/releases/20260730T195150Z-source/app/__init__.py
/opt/project-field-mouse/releases/20260730T195150Z-source/app/cli.py
```

After changing to the candidate root, the same interpreter imported `app`
successfully and resolved it to the candidate's `app/__init__.py`.

## Correction

The deployer now changes to the applicable release root before every
release-relative CLI invocation:

- candidate database migration;
- rollback database restore;
- backup from a previous production release.

It also has two explicit import assertions:

1. An early `import app` from the supplied source root before state copying or
   dependency installation.
2. An `import app` using the completed candidate virtual environment before
   migrations or unit installation.

Either assertion aborts through the existing transactional error handler.
Imports disable bytecode writes so the assertions do not modify staged source.

The patched script passed shell syntax validation on the Pi. Without invoking
migrations or deployment, the following checks passed from their explicit
roots:

- source-tree `import app`;
- candidate-venv `import app`;
- candidate-venv `python -m app.cli --help`.

No cutover retry was performed.

## Disk inventory

Read-only inspection after the stopped cutover found:

| Location | Size |
| --- | ---: |
| `/var/lib/fieldmouse/recordings` | approximately 14 GiB copied from legacy |
| `/opt/project-field-mouse/releases` | 2.0 GiB |
| dependency diagnostic environment | 2.1 GiB |
| recovery diagnostic | 20 MiB |
| initial diagnostic | 13 MiB |
| user pip cache | 194 MiB |

`/tmp` contained only small BirdNET session logs. `/var/tmp` contained no
remaining deployment package workspace. The filesystem remained about 90%
used with 5.7 GiB available.

No files, caches, recordings, failed releases, or rollback evidence were
deleted. Cleanup requires an explicit retention decision before another
cutover attempt.
