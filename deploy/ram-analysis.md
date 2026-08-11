# RAM Analysis — Raspberry Pi 3A+

Measured on the live stack, 2026-08-10. Hardware: Raspberry Pi 3 Model A+,
armv7l, 512 MB (**424 MB usable**), Raspberry Pi OS Lite 32-bit (trixie),
zram swap 423 MB. All eight containers running, database seeded.

**Headline: the containers are not the problem. Docker's own runtime is.**

Two rounds of measurement are recorded: **round 1** against the January-2025
DockerHub images, and **round 2** after rebuilding all images from
`race_meet_manager` and switching React to the nginx production build.

## Enabling measurement

`docker stats` reports `0B` out of the box on Raspberry Pi OS — the cgroup
memory controller is off by default. To measure anything you must add to the
**single line** in `/boot/firmware/cmdline.txt` and reboot:

```
cgroup_enable=memory cgroup_memory=1
```

RSS alone is misleading here because the machine swaps into zram, and swapped
pages leave RSS. The figures below add `memory.current` and
`memory.swap.current` from each container's cgroup to get true demand.

## How the swapping actually works — it is NOT a problem

**Swap here is compressed RAM, not the SD card.** The only swap device is
`/dev/zram0`. Measured:

```
orig_data   88,461,312 B  =  84.4 MB of pages handed to swap
compr_data  27,665,548 B  =  26.4 MB after compression
mem_used    29,949,952 B  =  28.6 MB of real RAM actually consumed
algorithm   zstd
```

84.4 MB of cold pages stored in 28.6 MB of RAM — **~2.95:1, a net saving of
~56 MB**. That is why `available` reads ~199 MB rather than ~143 MB.

**Why it swaps even though demand < total RAM.** It is not a shortage response:

- zram costs microseconds of CPU rather than disk I/O, so at the stock
  `swappiness=60` the kernel evicts cold anonymous pages freely whenever page
  cache would benefit. (`page-cluster=0` is zram-aware tuning — one page at a
  time, versus the disk-oriented default of 8.)
- Most of the swapped 84 MB is **container startup code that never runs again**.
  Eight containers start simultaneously at boot; `mem_used_max` (33.3 MB) sits
  above current (28.6 MB), confirming a peak that has since receded. Nothing
  pulls those pages back until something touches them.
- 155 MB of page cache is worth more than cold anon pages on a slow SD card.

**It is not thrashing.** `vmstat 2 4` shows `si`/`so` at **0** with the CPU 98%
idle. The distress signal would be sustained non-zero `si`/`so` — that is when
swap costs latency and would visibly hurt live MQTT updates. Check with
`vmstat 2 4` before concluding memory pressure exists.

> **Correction.** Earlier revisions of this document said "the stack does not fit
> in RAM." **That was wrong.** It fits comfortably; the kernel is *choosing* to
> compress cold pages because zram is nearly free real estate. A healthy
> optimisation was misread as a symptom, which overstated the case for every
> saving listed below — including the Docker question.

**`/var/swap` is not a stale file — do not delete it.**
`/sys/block/zram0/backing_dev` reads `/dev/loop0`, and `/var/swap` is the file
behind that loop device, wired up at boot by the stock
`rpi-setup-loop@var-swap.service`. It is zram's **writeback backing store**: when
a page proves incompressible or goes fully idle, the kernel can write it out
there and reclaim the RAM zram was holding. `bd_stat` reads `0 0 0` — nothing
has ever been written back on this workload — so it is pure insurance costing
424 MB of a 29 GB card. `dphys-swapfile` is not installed; this is a different
mechanism.

## Round 2 — current images (authoritative)

All images rebuilt from `race_meet_manager`; React on the nginx production build.

| Container | Resident | Swapped | **Total demand** | vs round 1 |
|---|---:|---:|---:|---|
| api | 44.0 MB | 9.6 MB | **53.6 MB** | +16.9 (real app: 39 routes) |
| database (Postgres 17, tuned) | 20.4 MB | 6.2 MB | **26.6 MB** | +4.9 |
| gpio-1 | 5.9 MB | 9.0 MB | **14.9 MB** | +3.6 |
| lapdata | 5.9 MB | 6.7 MB | **12.6 MB** | +1.0 |
| gpio-2 | 9.2 MB | 3.1 MB | **12.3 MB** | +1.0 |
| dbwriter | 2.5 MB | 7.7 MB | **10.2 MB** | −1.1 |
| **react (nginx static)** | 0.5 MB | 2.3 MB | **2.8 MB** | **−50.1** |
| mosquitto | 1.0 MB | 1.1 MB | **2.1 MB** | −0.1 |
| | | | **≈135 MB** | −24 MB |

| Docker runtime | RSS |
|---|---:|
| dockerd + containerd + 8 shims | **≈95 MB** |

System: **255 MB used, 77 MB swapped** (down from 108 MB). Total demand ~230 MB
against 424 MB physical.

**The headline result held.** Swapping React from the Vite dev server to the
nginx build saved **50 MB** — enough to absorb the current app being
substantially larger than the January-2025 build (the API nearly doubled to
53.6 MB with its full 39-route surface) and still come out ~24 MB ahead overall,
with 31 MB less swap pressure.

**The ranking has now changed**: `api` is the largest single consumer at 53.6 MB,
having overtaken everything else. Docker's runtime (~95 MB) still costs more than
any individual container. Postgres remains minor at 26.6 MB — reinforcing that
replacing it is the wrong target.

## Round 1 — January-2025 images (historical)

| Container | Resident | Swapped | **Total demand** |
|---|---:|---:|---:|
| react (Vite dev server) | 37.7 MB | 15.2 MB | **52.9 MB** |
| api | 20.2 MB | 16.5 MB | **36.7 MB** |
| database (Postgres 17, tuned) | 16.2 MB | 5.5 MB | **21.7 MB** |
| lapdata | 2.2 MB | 9.4 MB | **11.6 MB** |
| dbwriter | 3.5 MB | 7.8 MB | **11.3 MB** |
| gpio-1 | 2.0 MB | 9.3 MB | **11.3 MB** |
| gpio-2 | 2.6 MB | 8.7 MB | **11.3 MB** |
| mosquitto | 1.1 MB | 1.1 MB | **2.2 MB** |
| | | | **≈159 MB** |

| Docker runtime | RSS |
|---|---:|
| dockerd | 34.5 MB |
| containerd | 18.6 MB |
| containerd-shim × 8 | 61.1 MB (~7.6 MB each) |
| | **≈114 MB** |

Total process RSS: **290 MB**, with ~108 MB held in zram (costing rather less
than that in real RAM — see the swap section above).

## What this means

**Docker's runtime (114 MB) costs nearly as much as every container combined
(159 MB).** The eight `containerd-shim` processes alone are 61 MB, and that cost
scales linearly with container count — every service added costs ~7.6 MB before
it runs a single line of its own code.

## Ranked options

### 1. Replace the React dev-server image — ✅ DONE, measured 43 MB saved

**Result: 52.9 MB → 9.5 MB, with zero swap** (was 15.2 MB swapped).

Implemented by switching `build-and-push-react.ps1` to `Dockerfile.prod`. Three
fixes were needed to make that image actually work, which is why it was marked
"untested":

1. `Dockerfile.prod` had no `ARG`/`ENV` for the `VITE_*` vars, so they would have
   been `undefined` in the bundle. Now passed as build args.
2. It copied `./public` **over** `dist`, replacing the generated `index.html`
   (which references the hashed bundles) with a stale April-2024 template —
   a blank page. That `COPY` is removed; Vite already bundles `public/`.
3. `nginx.conf` used `try_files … =404`, which breaks every React Router deep
   link (`/nextrace`, `/racecontrol`, `/results/:id`) on load or refresh. Now
   falls back to `/index.html`.

It also builds far faster: `FROM --platform=$BUILDPLATFORM` runs `npm` natively
on the build machine instead of under QEMU emulation, since the output is
architecture-independent static files.

<details>
<summary>Original estimate</summary>

### 1. Replace the React dev-server image — saves ~45 MB
The published image is built from **`Dockerfile.dev`** and runs `npm run dev`: a
full Node + Vite dev server, with file watching on `usePolling: true` (which
also burns CPU). At 52.9 MB it is the largest single application.

`react/Dockerfile.prod` already exists and produces a static nginx image serving
a pre-built `dist`. That should land around 5–10 MB. Change
`build-and-push-react.ps1` to use `Dockerfile.prod`.

Caveat: with the prod build, `VITE_API_URL`/`VITE_MQTT_URL` become genuine
build-time constants baked into the bundle, so the address and port must be
fixed at build time.

</details>

### 2. Merge gpio-1 and gpio-2 into one container — ~19 MB. **Investigated only; deliberately NOT changed**
Two containers each run a Python interpreter (11.3 MB each) plus a 7.6 MB shim.

The one-container-per-lane design was chosen to get parallel lane monitoring
without writing threaded Python. Reviewing `gpio_to_timestamps.py`, the code
already uses interrupt-driven `GPIO.add_event_detect(..., callback=...)`, which
RPi.GPIO services on its own background thread — there is no sequential polling
loop, so a single process could register a callback per lane and get the same
concurrency for free.

**However, the separation does buy something real.** `handshake_end()` busy-waits:

```python
while flag1 != 1:
    flag1 = GPIO.input(lane["SELECTED"])
```

A tight Python spin loop holds the **GIL** (released only every ~5 ms by default).
In a shared process, one lane spinning there can delay another lane's callback
from starting — and `crossing_time = time.time_ns()` is the first statement in
that callback, so the delay lands straight on the timestamp. Separate processes
each have their own GIL and are genuinely parallel.

**If it were ever merged**, the prerequisite would be replacing the busy-wait
with `GPIO.wait_for_edge(lane["SELECTED"], GPIO.RISING)`, which blocks in C with
the GIL released. Only then is a single process safe.

**This does not scale up, so the 19 MB is a fixed cost, not a growing one.**
There are only ever **two physical lanes** with two GPIO sensors. The six
"lanes" elsewhere in the system are *digital* lanes identified by car ID over
the same two sensors — so `lanes[]` having two entries is correct and final, not
a partial implementation.

**Recommendation: leave it alone.** The GPIO layer is expected to be replaced
wholesale in the next iteration by reading lap data directly from the Scalextric
ARC Pro powerbase over Bluetooth LE (the `car_timestamp` contract is designed
for exactly this swap — see the architecture notes in `CLAUDE.md`). Refactoring
a component slated for replacement, in working code, ahead of a race meet, is a
poor trade. Revisit only if RAM becomes genuinely critical.

The two-container design **stands unchanged** — this entry records the analysis,
not a recommendation to act.

### 3. Reduce container count generally — ~7.6 MB each
Anything that merges services pays back a shim immediately.

### 4. Replace PostgreSQL with SQLite — saves ~15–20 MB. **Not worth it.**
This was the assumed big win; the measurement says otherwise. Postgres, with the
tuned settings already in `compose.race.yaml`
(`shared_buffers=16MB`, `max_connections=20`), costs **21.7 MB** — less than the
React dev server, and only marginally more than two GPIO containers.

Against that, the porting cost is real:

- `dbwriter/main.py` uses **psycopg2 with raw SQL** — a direct rewrite.
- `next_race.py` uses raw SQL that needs auditing for Postgres-only syntax.
- `database/schema.sql` is Postgres DDL (`SERIAL`, etc.).
- `api` and `dbwriter` both write, so SQLite needs WAL mode and busy-timeout
  handling.
- It would also remove the `psycopg2-binary` armv7 build problem (see below).

**Recommendation: do options 1 and 2 first.** Together they save ~64 MB, which
is more than three times what dropping Postgres would yield, for a fraction of
the risk. Re-measure before considering a database change.

## What is inside the `api` container? — measured, nothing to trim cheaply

`api` became the largest single consumer after the React fix, so it was worth
opening up. Measured by importing each library in turn inside the real image
(`docker run --rm --entrypoint python <api-image>`), reading `/proc/self/statm`
between imports:

| | Cost | Share |
|---|---:|---:|
| bare interpreter | 5.8 MB | 13% |
| `+ pydantic` | 4.8 MB | 11% |
| **`+ sqlalchemy`** | **13.3 MB** | **29%** |
| **`+ sqlmodel`** | **9.5 MB** | **21%** |
| `+ fastapi` | 7.9 MB | 18% |
| `+ psycopg2` | 2.2 MB | 5% |
| `+ uvicorn` | 1.5 MB | 3% |
| `+ starlette` | 0 MB | already pulled in by fastapi |
| **Total after imports** | **45.1 MB** | |

The running container's cgroup reports **45.6 MB** resident, so **the imports are
essentially the entire footprint** — application code and runtime data are a
rounding error on top of the libraries. It runs as a **single process**
(`fastapi run`, no worker multiplication), and the cgroup split is ~26.7 MB anon
(Python heap) against ~16.3 MB file-backed page cache.

**There is no silly waste here.** This is simply what `import fastapi` +
`import sqlmodel` costs on armv7.

The ORM stack is half of it — SQLAlchemy + SQLModel together are **22.8 MB**:

- Dropping **SQLModel** while keeping SQLAlchemy saves ~9.5 MB. Superficially
  attractive since no relationships are defined and complex queries already use
  raw SQL — but it is threaded through `model.py`, `responsemodel.py` and every
  endpoint.
- Dropping **SQLAlchemy** for raw psycopg2 (as `dbwriter` already does) saves
  ~23 MB and is a rewrite of the data layer.
- FastAPI + pydantic (12.7 MB) are unavoidable while this API exists.

**Conclusion: don't.** Every option is a substantial refactor for 10–23 MB,
against Podman's ~75–85 MB for a mechanical migration (below). If headroom is
ever needed, Podman first, the ORM a distant second.

## Is it worth ditching Docker in production?

Asked because Docker's runtime is the largest single line in the budget. Short
answer: **viable, worth ~100–120 MB, but not yet worthwhile — and the specific
hybrid of "Docker in dev, native in prod" is the option to avoid.**

### Measured inputs

- **Four distinct Python base images** (`api`, `lapdata`, `dbwriter`, `gpio`).
  `gpio-1`/`gpio-2` share one image, so those pages *are* shared; the other
  three each carry their own interpreter and site-packages.
- **Native Python on the Pi is 3.13.5, ~6.7 MB RSS** for a bare interpreter.
- **`postgresql 17` and `mosquitto 2.0.21` are both packaged for this OS**, so a
  native path genuinely exists rather than being hypothetical.

| | Containerised (measured) | Native (estimated) |
|---|---:|---:|
| Docker runtime | 95 MB | **0** |
| Python services (5 processes) | 104 MB | ~85 MB — one shared interpreter, not 4 copies |
| Postgres / nginx / mosquitto | 31 MB | ~30 MB |
| **Total** | **~230 MB** | **~115 MB** |

### Why not to do it

Going native in production while developing on Docker means **the thing you test
is no longer the thing you ship**. This repo has already been bitten by that four
times, all discovered on 2026-08-10/11:

1. The React image was built from `Dockerfile.dev` — production ran a **Vite dev
   server for 18 months**.
2. `dbwriter` had no published image, so `compose.pi.yaml` deployments had **no
   lap persistence at all**.
3. `psycopg2-binary` has no `armv7l` wheel — surfaced only on the target.
4. `Dockerfile.prod` was broken (`COPY ./public` overwriting the generated
   `index.html`) and was marked "untested".

Every one is a dev/prod divergence bug. Making that divergence deliberate and
permanent institutionalises the failure mode that has already cost the most time.

### The middle path: Podman

**The artifact is the image, not the daemon.** Podman is daemonless — no
`dockerd` (34.5 MB), no `containerd` (18.6 MB) — and `conmon` costs ~1–2 MB per
container against `containerd-shim`'s 7.6 MB.

Estimated saving **~75–85 MB**, most of the prize, while keeping OCI images,
compose-compatible workflows, atomic rollback, and *the same artifact in dev and
prod*. Docker-in-dev / Podman-in-prod is a safe hybrid precisely because the
image is identical. Native-in-prod discards the artifact, which is where parity
dies.

### Recommended order

1. **Nothing.** ~199 MB available, `si`/`so` at zero, zram *saving* ~56 MB. There
   is no pressure to relieve, and the Zero 2 W target is already met. Don't spend
   a weekend reclaiming memory you aren't short of.
2. **Podman**, if real headroom is ever needed — ~75–85 MB for a mechanical
   migration that keeps the image as the shared artifact.
3. **The ORM stack**, a distant third: ~9.5 MB to drop SQLModel, ~23 MB to drop
   SQLAlchemy entirely, both substantial refactors (see the `api` section above).
4. **Native**, only if 2 and 3 are insufficient — and then go native in dev too.

> An earlier revision of this list ranked "investigate `api`" *above* Podman on
> the grounds that trimming one process is cheaper than changing deployment.
> That was wrong twice over. The investigation has now been done and found
> nothing cheap to trim — the footprint is library imports, not waste — and
> Podman was always the larger, more mechanical win. Recorded because the
> reasoning error is more instructive than the conclusion.

### Before migrating to Podman, note

Podman is daemonless, so **nothing restarts containers on boot** — that duty
moves to systemd (`podman-restart.service` or Quadlet units). Given that
unattended recovery after a power cut is a hard requirement here (see
`race-network-setup.md`), a real reboot test is the acceptance criterion, not an
afterthought. Also expect to handle: named volumes do not transfer from Docker
(`postgres_data` needs migrating or re-seeding), `privileged: true` GPIO access
wants rootful Podman rather than rootless, and compose fidelity varies between
`podman compose` and `podman-compose`. Docker and Podman can coexist, so a trial
is reversible — but not on the eve of a meet.

## Pi Zero 2 W feasibility

The Zero 2 W has the same 512 MB, so the arithmetic is identical (its CPU is
comparable — quad-core A53 — so zram compression is not markedly worse). It does
not change the Docker question above; it only removes the margin worth keeping
for the BLE/ARC Pro work.

- **Round 2 (current):** ~230 MB demand, ~89 MB in zram costing ~29 MB of real
  RAM, ~199 MB available, and `si`/`so` at zero. It runs with headroom.
- **After option 2:** roughly 20 MB better again.

So the Zero 2 W target is **already realistic** now that the React image is
fixed — not contingent on further work.

Note the earlier framing here ("under swap pressure, which adds latency exactly
where it hurts") was wrong for the same reason as the correction above: pages
resident in zram are not pressure, and there is no measured swap-in/swap-out
traffic. Latency would only suffer if `vmstat` showed sustained `si`/`so`, which
is the thing to check before believing memory is the problem.

## Related build note

`psycopg2-binary` publishes no `armv7l` wheel, so on 32-bit Pi OS it compiles
from source. `dbwriter/Dockerfile` installs `gcc`, `libc6-dev` and `libpq-dev`
to make that work; the build takes ~7 minutes on this hardware, dominated by
installing the toolchain rather than the compile itself.

A **64-bit** Pi OS would avoid this entirely — `aarch64` wheels are published.
Worth considering if the SD card is ever rebuilt, though note that 64-bit
slightly increases baseline memory use, which cuts against the goal above.
