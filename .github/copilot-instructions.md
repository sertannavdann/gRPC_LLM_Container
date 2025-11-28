# Development Guidelines

## Pre-Implementation Analysis Protocol: ** Before writing any code **

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