# Run Local Bookkeeper with Docker

Use Docker Desktop with Linux containers, or Docker Engine with the Compose
plugin. From the repository folder:

```powershell
docker compose up -d --build
```

Open <http://127.0.0.1:8766/>. Port 8766 keeps this instance separate from the
native Python app on port 8765. The published port is bound to this computer's
loopback interface. The app still checks Host and Origin headers.

## First profile and storage

On the setup screen, choose **Create profile**, use
`/data/profiles/My books`, and enter a profile and first business name. Other
profiles can use `/data/profiles/Another profile`. Paths in this screen are
container paths; native Windows/macOS folder pickers are unavailable in Docker.
CSV/XLSX statement upload still uses your browser's normal file chooser.

The project-local `bookkeeper-data` folder stores everything mounted under `/data` in the
container:

```text
/data/
  config/settings.json       # Last profile and recent locations
  profiles/My books/
    bookkeeper.profile.json
    bookkeeper.sqlite3       # Transactions, saved rules and preferences
    documents/
```

If this app was previously run with the older named Docker volume, the old
profiles remain in that volume and are not copied automatically. Before the
first start with this updated Compose file, copy them into the new `bookkeeper-data` folder
from PowerShell in the project folder:

```powershell
docker compose stop
docker run --rm -v local-bookkeeper_bookkeeper_data:/source -v "${PWD}/bookkeeper-data:/destination" alpine sh -c "cp -a /source/. /destination/"
```

If you have no existing profiles, no migration is needed.

`docker compose down` stops and removes the container but leaves the `bookkeeper-data`
folder in place. Use **Data & storage → Download profile backup** for a portable
backup containing the database, rules, preferences and original statements.

## Keep live data separate from test files

Use these locations in the project folder:

| Host folder | Contents |
| --- | --- |
| `bookkeeper-data/config/` | Active Docker settings and recent profile locations |
| `bookkeeper-data/profiles/` | Live profiles, databases, rules JSON and retained statements |
| `tests/fixtures/` | Synthetic JSON samples and other committed test inputs |
| `outputs/` | Temporary exports, scratch JSON and test output; ignored by Git |
| `data/` | Previous local files, kept untouched until reviewed or migrated |

Only `bookkeeper-data/` is mounted into Docker at `/data` by default. Keep each
profile folder together: its JSON files may be required profile locators or rules,
so a JSON extension alone does not mean a file is unused. Private data in
`bookkeeper-data/`, `data/` and `outputs/` is excluded from Git and image builds.

If your current profiles are in the old `data/` folder, download a backup from
the running app before switching, then restore into `/data/profiles/Restored books`
using the steps below. Export rules JSON separately as described below. Leave the
old folder in place until you have confirmed the restored profile. If you already
set `BOOKKEEPER_DATA_DIR` in `.env`, that setting continues to select your existing
folder; change it explicitly when you are ready to switch.

## Bring an existing profile into Docker

In the Docker app, choose **Restore export / backup** and use **Choose an
exported profile file** to upload a reusable Excel ledger, a SQLite export or a
profile backup ZIP from your browser (up to 20 MB). Set the new destination to
`/data/profiles/Restored books`. Categories, saved decisions and preferences
resume in the new profile. Only a direct SQLite restore includes rules. Excel
and ZIP restores exclude them; use **Rules & automation → Import JSON** to add
rules separately. A backup ZIP also transfers original statement files.

For larger files, or to use a file already on the Docker host:

The native app's Windows profile path is not visible inside a Linux container.
Use the native app's **Download profile backup**, then copy that ZIP into the
running Docker instance:

```powershell
docker compose cp "C:/Backups/my-profile.zip" bookkeeper:/data/import.zip
```

In Docker's setup/profile screen, choose **Restore export / backup**, then **Or choose a file already on the server**:

- Backup: `/data/import.zip`
- New destination: `/data/profiles/Restored books`

Restore opens a copy with the existing transactions, categories and preferences.
Import rules JSON separately, or restore the extracted SQLite database to retain
its rules. The native profile stays in its original location. Reopen the Docker
copy later using `/data/profiles/Restored books/bookkeeper.profile.json`.

## Choose a different host folder

The default is `./bookkeeper-data` beside `compose.yaml`. To use a different folder:

1. Copy `.env.example` to `.env`.
2. Set `BOOKKEEPER_DATA_DIR` to an existing absolute folder. On Windows, use forward
   slashes, for example `C:/BookkeeperData`.
3. Start the app as usual:

```powershell
docker compose up -d --build
```

Both profile data and `config/settings.json` are kept in that host folder. If you
change the folder after creating profiles, the old folder remains untouched; use
backup and restore to move profile data.

If the chosen host folder already contains a profile, choose **Open profile** and
enter `/data/bookkeeper.profile.json` (or its actual relative location under
`/data`). Stop the native app before directly sharing its books folder with
Docker. Prefer a backup restore for separate native and Docker copies.

The image runs as user/group `10001:10001`. A Linux bind folder must be writable
by that user. For a new, empty Linux data folder, you can create it with:

```sh
sudo install -d -o 10001 -g 10001 /srv/local-bookkeeper
```

Windows Docker Desktop folder permissions are managed through Docker Desktop.

## Change the port

Copy `.env.example` to `.env` and change `BOOKKEEPER_PORT`, then recreate the
container:

```powershell
docker compose up -d
```

Compose updates both the published port and the accepted browser Host headers.
The container continues listening on port 8765 internally.

## Logs, stop and update

```powershell
docker compose logs -f bookkeeper
docker compose ps
docker compose stop
docker compose up -d --build
```

The health check calls `/api/health`. An instance waiting for first-time profile
setup is healthy. Application/image updates reuse the data volume; take a profile
backup before upgrading the app.

## Container configuration

The Dockerfile sets:

| Variable | Default in the image | Purpose |
| --- | --- | --- |
| `LOCAL_BOOKKEEPER_HOST` | `0.0.0.0` | Listen on container network interfaces |
| `LOCAL_BOOKKEEPER_PORT` | `8765` | Internal HTTP port |
| `LOCAL_BOOKKEEPER_ALLOWED_HOSTS` | Set by Compose | Additional comma-separated `host:port` browser addresses |
| `LOCAL_BOOKKEEPER_CONFIG` | `/data/config/settings.json` | Remember the selected profile |
| `LOCAL_BOOKKEEPER_DATA` | `/data` | Find existing books mounted at `/data` |
| `LOCAL_BOOKKEEPER_BOOKS_DIR` | `/data/profiles/My books` | Suggested new profile directory |
| `LOCAL_BOOKKEEPER_STORAGE_ROOT` | `/data` | Keep new profile destinations on persistent storage |

For `docker run` without Compose, build and configure the mapped browser port
explicitly:

```powershell
docker build -t local-bookkeeper:local .
docker run -d --name local-bookkeeper --init --restart unless-stopped -p 127.0.0.1:8766:8765 -e LOCAL_BOOKKEEPER_ALLOWED_HOSTS=127.0.0.1:8766,localhost:8766 -v bookkeeper_data:/data local-bookkeeper:local
```

The build context allows only named runtime source files. Databases, statements,
profiles, backups, local environment files and Git history are excluded from the
image. The application uses SQLite directly; no separate database container is
required.

Reference: [Docker Compose service configuration](https://docs.docker.com/reference/compose-file/services/)
and [container storage mounts](https://docs.docker.com/engine/containers/run/#filesystem-mounts).
