# Development Guidelines

**Always reuse existing code - no redundancy!**

## Tech Stack

- **Runtime**: Node 22+ (Bun also supported for dev/scripts)
- **Language**: TypeScript (ESM, strict mode)
- **Package Manager**: pnpm (keep `pnpm-lock.yaml` in sync)
- **Lint/Format**: Oxlint, Oxfmt (`pnpm check`)
- **Tests**: Vitest with V8 coverage
- **CLI Framework**: Commander + clack/prompts
- **Build**: tsdown (outputs to `dist/`)

## Anti-Redundancy Rules

- Avoid files that just re-export from another file. Import directly from the original source.
- If a function already exists, import it - do NOT create a duplicate in another file.
- Before creating any formatter, utility, or helper, search for existing implementations first.

## Source of Truth Locations

### Formatting Utilities (`src/infra/`)

- **Time formatting**: `src\infra\format-time`

**NEVER create local `formatAge`, `formatDuration`, `formatElapsedTime` functions - import from centralized modules.**

### Terminal Output (`src/terminal/`)

- Tables: `src/terminal/table.ts` (`renderTable`)
- Themes/colors: `src/terminal/theme.ts` (`theme.success`, `theme.muted`, etc.)
- Progress: `src/cli/progress.ts` (spinners, progress bars)

### CLI Patterns

- CLI option wiring: `src/cli/`
- Commands: `src/commands/`
- Dependency injection via `createDefaultDeps`

## Import Conventions

- Use `.js` extension for cross-package imports (ESM)
- Direct imports only - no re-export wrapper files
- Types: `import type { X }` for type-only imports

## Code Quality

- TypeScript (ESM), strict typing, avoid `any`
- Keep files under ~700 LOC - extract helpers when larger
- Colocated tests: `*.test.ts` next to source files
- Run `pnpm check` before commits (lint + format)
- Run `pnpm tsgo` for type checking

## Stack & Commands

- **Package manager**: pnpm (`pnpm install`)
- **Dev**: `pnpm openclaw ...` or `pnpm dev`
- **Type-check**: `pnpm tsgo`
- **Lint/format**: `pnpm check`
- **Tests**: `pnpm test`
- **Build**: `pnpm build`

If you are coding together with a human, do NOT use scripts/committer, but git directly and run the above commands manually to ensure quality.

## Pre-Implementation Analysis Protocol: **Before writing any code**

### ANALYSIS_REQUIRED:
1. Map the dependency tree of affected components
2. Identify all touchpoints and side effects
3. Locate redundant features that can be removed
4. Plan cleanup alongside implementation
5. Verify changes maintain architectural consistency
### Dependency Checklist:
- Trace all imports and exports
- Identify data flow dependencies
- Map component relationships
- Check for circular dependencies
- Analyze test coverage impact

## Code Modification Guidelines : ** When implementing changes ** 

### IMPLEMENTATION_RULES:
- Make surgical, focused changes only to required sections
- Delete deprecated functionality immediately
- Update all related documentation simultaneously  
- Refactor for clarity as you go
- Maintain single responsibility principle

### Red Flag Detection:
- Functions/methods exceeding 20 lines
- Components with multiple responsibilities
- Duplicate logic patterns
- Unused variables or imports
- Complex nested conditionals

## Cleanup & Refactoring Protocol: **For every feature modification**

### CLEANUP_REQUIRED:
1. Remove obsolete functions and components
2. Delete unused dependencies and imports
3. Update or remove outdated tests
4. Simplify complex conditionals and loops
5. Consolidate duplicate logic
6. Verify no dead code remains

### Complexity Control Measures:    
- Break large components into focused sub-components
- Extract complex logic into pure utility functions
- Flatten nested structures where possible
- Eliminate unnecessary state and side effects

## Architecture Maintenance: **High-Level Design (HLD) Requirements:**


### ARCHITECTURE_RULES:
- Maintain ONE source of truth for system architecture
- Update HLD with every significant change
- Ensure visual clarity of component relationships
- Document data flow and state management
- Keep dependency graphs current

### HLD Components to Maintain:
- System component diagram
- Data flow mapping
- API contract documentation
- State management structure
- External dependency inventory

## Code Review Checklist: ** For every PR and change **

### REVIEW_CRITERIA:
✅ Changes are minimal and focused
✅ Dependency impacts are addressed
✅ Redundant code is removed
✅ Code readability is maintained or improved
✅ Tests are updated appropriately
✅ Documentation reflects changes
✅ No complexity introduced unnecessarily


## Agentic Development Guardrails: Prevent Complexity Creep:

### GUARDRAILS:
- Reject solutions that increase technical debt
- Flag architectural inconsistencies immediately
- Require simplification proposals for complex code
- Mandate cleanup for feature alterations
- Enforce consistent patterns across codebase

### Complexity Metrics to Monitor:
- Cyclomatic complexity per function
- File size and responsibility scope
- Import dependency depth
- Component coupling levels
- Test coverage of critical paths