# dex-studio (the DataEngineX runtime)

Layer 1 of the DataEngineX rebuild: the runtime app that loads a
DataEngineX project and runs it.

    dataenginex init      create a starter project
    dataenginex check     validate definitions without running
    dataenginex run       run pipelines (Bronze / Silver / Gold)
    dataenginex receipt   show the receipt of a run
    dataenginex serve     local read API over Gold (later)

The CLI command is `dataenginex` (decision 0012 in the dataenginex
repo). The name `dex` belongs to the AI assistant product
(decision 0023) - do not use it for this runtime.

Rules:
- Depends on the dataenginex foundation package (Layer 0) through its
  public API only. Shipped builds install dataenginex from PyPI,
  pinned by minor version - never from a sibling folder.
- The same runtime image runs locally and in the cloud. Nothing in
  this repo may become cloud-only.
- No domain logic here. Domain apps live in their own repos (Layer 2).

Status: fresh start (2026-10-28). The previous dex-studio codebase,
including its unpushed local commits, was removed in full at the
founder's direction. Skeleton only - the CLI lands with the M0/M1
milestones of the foundation package.
