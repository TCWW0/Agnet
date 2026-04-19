---
mode: agent
model: Claude Sonnet 4
---

<!-- markdownlint-disable-file -->

# Implementation Prompt: Agent 前后端联调（第一版）

## Implementation Instructions

### Step 1: Create Changes Tracking File

You WILL create `.copilot-tracking/changes/20260418-agent-frontend-integration-changes.md` if it does not exist.

### Step 2: Execute Implementation

You WILL follow .copilot-tracking/plans/20260418-agent-frontend-integration-plan.instructions.md
You WILL systematically implement tasks described in .copilot-tracking/details/20260418-agent-frontend-integration-details.md
Follow ALL project standards and conventions (typing, pydantic models for message, adapter pattern in `frame.core.openai_adapter`).

**CRITICAL**: If ${input:phaseStop:true} is true, stop after each Phase for user review.
**CRITICAL**: If ${input:taskStop:false} is true, stop after each Task for user review.

### Step 3: Cleanup

When ALL Phases are checked off (`[x]`) and completed you WILL do the following:

1. Provide a brief summary of changes and create a markdown link to the changes file.
2. Provide markdown links to .copilot-tracking/plans/20260418-agent-frontend-integration-plan.instructions.md, .copilot-tracking/details/20260418-agent-frontend-integration-details.md, and .copilot-tracking/research/20260417-frontend-chatgpt-style-research.md
3. Attempt to delete this prompt file from .copilot-tracking/prompts when implementation completes.

## Success Criteria

- [ ] Changes tracking file created
- [ ] All plan items implemented with working code
- [ ] All detailed specifications satisfied
- [ ] Project conventions followed
- [ ] Changes file updated continuously
