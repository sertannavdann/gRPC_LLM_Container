"""
Approval policy scaffold for module lifecycle gating (D-18).

This module defines forward-compatible configuration for auto-approval
semantics. It is a scaffold only: no code path in this phase reads
`auto_approve` to skip the manual approval gate. The hard default of
`auto_approve=False` reflects D-16 — module install always requires
explicit human approval until a future phase deliberately activates
policy-driven automation.
"""
from typing import List

from pydantic import BaseModel


class ApprovalPolicy(BaseModel):
    """
    Policy controlling module approval automation.

    Fields are forward-compatible scaffolding for a future auto-approve
    relaxation; none are wired into the approval/install code paths yet.
    """

    auto_approve: bool = False
    trusted_categories: List[str] = []
    require_all_tests_pass: bool = True


DEFAULT_APPROVAL_POLICY = ApprovalPolicy()
