# Run EuroBIS QC in Docker

The image contains the project source and command-line dependencies. The
single `qc` service starts an idle container; jobs are started from a shell in
that container (Portainer Console or Docker Desktop Exec tab). Jobs update the
configured SQL Server database and stop when they finish. Between jobs the
container only runs `sleep` and uses no noticeable resources.

## Setup

1. Install Docker with Docker Compose.
2. Configure `../dbworks/resources/config.ini` as described in
   [README.md](../README.md). Use
   `drivermodule = pymssql` for this image. The Microsoft ODBC driver is not
   installed. Use a SQL Server address reachable from the container;
   `127.0.0.1` refers to the container itself.
3. Ensure `../dbworks/database/EUROBIS_QC_LOOKUP_DB.db` exists and contains the
   taxonomy data. The SQLite directory must be writable: `process_list.py`
   refreshes the resource lookup tables before calculating QC.
4. Build and start the container from this `docker/` directory:

```sh
cd docker
mkdir -p ../output
docker compose build
docker compose up -d
```

Run every `docker compose` command in this document from the `docker/`
directory, where `compose.yaml` is. From the repository root, add
`-f docker/compose.yaml` instead, for example
`docker compose -f docker/compose.yaml build`.

Database credentials and the SQLite database are excluded from the image and
mounted from the host at runtime. CSV output is saved in `../output`.

The code is copied into the image. After changing the code, rebuild and
recreate the container:

```sh
docker compose build
docker compose up -d
```

`docker compose down` stops and removes the container; the image is kept.

## Run a job

Open a shell in the running `qc` container:

- **Portainer:** Containers → the `qc` container → Console → Connect.
- **Docker Desktop:** Containers → `eurobis-qc-python` → `qc` → Exec tab.
- **Terminal:** `docker compose exec qc sh`

The shell starts in `/output`. Then run one of the commands below.

### Calculate QC, then fitness labels

```sh
python -m eurobisqc.examples.process_list --providers 1470 1471 1472
python -m eurobisqc.examples.process_all
```

`process_list` processes the providers given with `--providers` (default `1`)
and then calculates their fitness labels. `process_all` does the same for all
dataproviders. Fitness labels are only calculated if the QC step succeeds.
Dataset fitness calculations remain separate for each provider. Unlabelled
record labels are SQL `NULL`.

`process_list` runs in one process. `process_all` processes the datasets in
parallel: by default it starts one process less than the CPUs of the container
(`cpus:` in `compose.yaml`), or three less with `server_local = True`, and at
least one. Set `QC_PROCESSES` to choose the number yourself. Every process
holds its own dataset in memory, so they all share `mem_limit`:

```sh
QC_PROCESSES=2 python -m eurobisqc.examples.process_all
```

If one of the processes dies, for instance because it was killed for using too
much memory, `process_all` stops all processes with a `BrokenProcessPool`
error and logs the datasets that did not complete. These can be processed again
with `process_list --providers ...`. The fitness labels are not calculated then.

### Fitness labels only

To calculate only the fitness labels from the QC flags already stored in the
database, run `fitness_for_use` on its own. Use `--providers` to select
dataproviders (default `1476`) or `--all` for all of them:

```sh
python -m eurobisqc.examples.fitness_for_use --providers 1470 1471 1472
python -m eurobisqc.examples.fitness_for_use --all
```

### Long runs

Output is only shown in the open console; closing it stops the job. For long
runs, such as `process_all`, run the job in the background and write the
output to a log file in `../output`:

```sh
nohup sh -c 'python -m eurobisqc.examples.process_all; echo "exit code: $?"' > /output/process_all.log 2>&1 &
nohup python -m eurobisqc.examples.process_all > /output/run.log 2>&1 &
tail -f /output/run.log
```

### Without opening a shell

From the `docker/` directory, a job can also be run in a separate container
that is removed when the job finishes:

```sh
docker compose run --rm qc python -m eurobisqc.examples.fitness_for_use --providers 1476
```

## Deploy on a server

The repository is cloned into your own folder on the server and the image is
built there; no CI/CD, container registry or Portainer stack is needed. The
container started there shows up in Portainer (as a stack created outside
Portainer), where jobs are run from the Console.

### First installation

```sh
cd <your-folder>
git clone https://github.com/lifewatch/eurobis-qc.git
cd eurobis-qc/docker
mkdir -p ../output
```

Then add the files that are not part of the repository or the image:

1. Edit `../dbworks/resources/config.ini` with the server's SQL Server address
   and credentials (see Setup). The repository contains a template of this
   file, so stop Git from tracking the local edits:

   ```sh
   git update-index --skip-worktree ../dbworks/resources/config.ini
   ```

2. Copy `EUROBIS_QC_LOOKUP_DB.db` to `../dbworks/database`, for example:

   ```sh
   scp EUROBIS_QC_LOOKUP_DB.db user@server:<your-folder>/eurobis-qc/dbworks/database/
   ```

3. Build and start the container:

   ```sh
   docker compose build
   docker compose up -d
   ```

### Update to the latest code

```sh
cd <your-folder>/eurobis-qc/docker
git pull
docker compose build
docker compose up -d
```

`docker compose up -d` replaces the container with one using the new image.
`config.ini`, the SQLite database and `../output` stay in place. If `git pull`
reports a conflict on `config.ini` because the template changed, back up the
file, run `git update-index --no-skip-worktree ../dbworks/resources/config.ini`
and `git checkout ../dbworks/resources/config.ini`, pull again, restore your
settings, then repeat the `--skip-worktree` step.

Each build leaves the previous image behind as an untagged `<none>` image.
Remove these with `docker image prune` (without `-a`, which would also remove
other unused images on the server).

### Notes for a shared server

- Without a restart policy, the container stays stopped after a server or
  Docker restart. Start it again in Portainer, or add
  `restart: unless-stopped` to the `qc` service in `compose.yaml`.
- Users running jobs from the terminal need permission to run Docker
  (membership of the `docker` group or `sudo`). Portainer users only need
  access to the container in Portainer.

## Other project scripts

Any other command-line module runs the same way from the container shell:

```sh
python -m eurobisqc.examples.run_mssql_whole_db
```

Desktop file chooser examples need a display and PySimpleGUI, which this
headless image does not install. API-backed checks require outbound network
access.

The image installs the project's Git-based dependencies from their configured
repositories, so building requires network access. Python 3.11 and a compatible
setuptools version support the existing legacy dependencies.
