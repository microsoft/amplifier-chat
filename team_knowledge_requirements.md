# Team Knowledge Base: Comprehensive Requirements from Design Document

This document provides a structured breakdown of all features, requirements, and components as described in `2026-03-11-team-knowledge-base-design.md`.

## 1. Core Principles & Architecture

- **Storage Backend**: Must be a git-hosted repository.
    - **Rationale**: No new infrastructure, versioned by default, works offline, enables stigmergic coordination.
- **Data Model**: The system is for static, consumable data (what exists, patterns), complementing `session-sync` which handles dynamic data (what's happening now).
- **Layered Discovery (Anti-Bloat Design)**: Agents must not load the entire repository. Discovery must be progressive.
    - **Layer 0**: A single manifest file (`manifest.yaml`) as the entry point, containing a high-level index of all people, capabilities, and conventions.
    - **Layer 1**: Individual, small capability files that are read on-demand based on information from the manifest.
    - **Layer 2**: Full detail documents (conventions, dotfiles) read only after an agent deems them relevant.
- **Target Token Cost**: A typical query should result in reading ~200 lines of text, not thousands.

## 2. Repo Structure

The knowledge base git repo must have the following directory and file structure:

- **`/manifest.yaml`**: The Layer 0 entry point.
    - Lists every person, capability, and convention by name.
    - Includes a one-liner description for each entry.
    - Includes `last-updated` timestamps for each entry.
- **`/people/<github-handle>/`**: Directory for each team member.
    - **`profile.yaml`**: Contains repos, ownership, skills, and team affiliation. Should be 20-30 lines.
    - **`activity.md`**: Generated from `session-sync` data, showing recent work summaries.
- **`/capabilities/<name>.yaml`**: One file per discovered capability.
    - Describes what it does, where it lives, how to use it, and who owns it.
    - **Schema Fields**: `name`, `description`, `repo`, `path`, `owner`, `type` (bundle, plugin, tool, convention, pattern), `usage`, `dependencies`.
- **`/conventions/<name>.md`**: Human-curated, team-approved patterns and standards.
    - **NOT auto-generated**.
    - Examples: `how-to-write-a-distro-plugin.md`, `testing-standards.md`.
- **`/dotfiles/<github-handle>/`**: Directory for data formatted for Brian Krabach's visualization tools.
- **`/index/`**: Directory for the local search index.
    - **`vectors.bin`**: The binary vector database file. Must be committable to git.
    - **`vectors.meta.json`**: Metadata for the index.
- **`/tools/`**: Directory for the generation and maintenance scripts.

## 3. Generation Pipeline & Tooling

A set of Python scripts to automate knowledge base population.

- **`generate-person.py`**:
    - Scans a person's local repositories for capabilities.
    - Identifies capabilities from `pyproject.toml`, bundle YAML, `AppManifest` files, and recipe YAML.
    - Writes/updates `/people/<handle>/profile.yaml`.
    - Writes/updates `/dotfiles/<handle>/`.
    - Writes/updates `/capabilities/<name>.yaml` for each discovered item.
    - Must be incremental, using git history (`git log --since`) to only re-scan changed repos.
    - Calls `rebuild-index.py` after making changes.
- **`sync-activity.py` (Phase B)**:
    - Pulls recent session data from the `session-sync` metrics API.
    - Must use a "since" timestamp for incremental updates.
    - Writes to `/people/<handle>/activity.md`.
- **`index-capabilities.py`**:
    - A focused script to scan for bundles/plugins/tools and write to `/capabilities/`. (Note: The doc also says `generate-person.py` does this).
- **`rebuild-index.py`**:
    - Regenerates the local vector index from all YAML and Markdown files in the repo.
    - Must be incremental, using file hashes to only re-index changed files.
    - Must support a full rebuild option.
- **Vector DB Requirements**:
    - Must be embeddable (no server).
    - Must be git-friendly (binary file can be committed).
    - Options to investigate: DuckDB vss, sqlite-vec, FAISS.

## 4. Update Model

- **Trigger**: The generation pipeline must be triggered automatically on `git push`.
- **Mechanism**: A `post-push` git hook.
- **Flow**:
    1. Developer pushes code to a project repository.
    2. `post-push` hook runs `generate-person.py`.
    3. Script finds changes and updates files in the team knowledge repo.
    4. Script commits the changes to the shared knowledge repo.

## 5. Consumer Interface: `team_knowledge` Bundle

A new Amplifier bundle (`amplifier-bundle-team-knowledge`) to provide the primary agent interface.

- **`team_knowledge` Tool**:
    - Provides a programmatic query interface abstracting the storage backend.
    - **`search(query: str)` operation**:
        - Performs semantic search using the local vector index.
        - Must return 3-5 ranked results (capability files).
        - Must NOT be simple substring matching.
    - **`lookup(name: str)` operation**:
        - Returns the full content of a specific capability file.
    - **`list(category: str)` operation**:
        - Returns entries from `manifest.yaml` filtered by category (e.g., "conventions").
        - Returns only names and one-liner descriptions.
    - **`publish(name: str, content: dict)` operation (Phase C)**:
        - Allows an agent to write a new capability file.
        - Must trigger `rebuild-index.py`.
        - Must commit the new file to the repo.
- **Session Start Hook (Phase C)**:
    - On session start (specifically, Phase C of the session lifecycle), a hook should run.
    - It reads `manifest.yaml`.
    - It injects a *thin* context summary into the agent's context (e.g., "Your team has N capabilities... Use `team_knowledge` to query.").

## 6. Data Flows

The design specifies three distinct data flow patterns.

- **Read Path (Agent Querying)**:
    - **Manual Flow**: Agent reads `manifest.yaml`, identifies relevant capabilities, then reads specific `/capabilities/<name>.yaml` files.
    - **Tool-based Flow**: Agent calls `team_knowledge(operation="search", ...)`, the tool queries the vector index and returns ranked capability files for the agent to read.
- **Write Path (Manual Publishing)**:
    - Agent calls `team_knowledge(operation="publish", ...)`.
    - The tool writes the capability file, rebuilds the index, and commits.
- **Generation Path (Automated)**:
    - A `git push` triggers the `post-push` hook.
    - The `generate-person.py` script scans repos, writes updated files, rebuilds the index, and commits to the knowledge repo.

## 7. Testing Strategy

- **Unit Tests**:
    - For generation tools using fixture repositories.
    - For the query interface tool with a mock vector index.
- **Integration Tests**:
    - `generate-person` running against a real repository clone.
- **End-to-End Test**:
    - A full pipeline test: create a test repo, run generation, run indexing, and verify that the `search` tool returns the correct results.
- **Bundle Integration Test**:
    - Verify that composing the `team_knowledge` bundle correctly installs the tool and makes it available to an agent.

## 8. Phased Delivery

- **Phase A (Smart Repo)**:
    - Build the repo structure.
    - Build the core generation tools (`generate-person`, `rebuild-index`).
    - Implement the local vector index.
    - Create the `team_knowledge` bundle with the query tool (search, lookup, list).
    - Implement the `post-push` hook.
- **Phase B (Session-Sync Integration)**:
    - Build the `sync-activity.py` tool.
    - Extend `session-sync` to index the knowledge repo's content.
- **Phase C (Ambient Plugin)**:
    - Implement the session-start hook for context injection.
    - Implement the `publish` operation in the `team_knowledge` tool.
    - Create a distro server or `amplifierd` plugin to serve the query interface over HTTP.
