"""
Eval Runner for Tool Selection and Response Quality.

Loads YAML eval cases and measures:
- Tool selection accuracy
- Argument correctness
- Multi-step query handling
- Clarification detection

Usage:
    python -m tests.evals.eval_runner
    python -m tests.evals.eval_runner --suite tool_selection
    python -m tests.evals.eval_runner --difficulty easy,medium
"""

import argparse
import fnmatch
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Result of a single eval case."""
    case_id: str
    passed: bool
    tool_selection_correct: bool
    argument_correct: bool
    latency_ms: float
    expected_tools: List[str]
    actual_tools: List[str]
    expected_args: Dict[str, Any]
    actual_args: Dict[str, Any]
    error: Optional[str] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class EvalSummary:
    """Summary of eval run."""
    total_cases: int
    passed: int
    failed: int
    tool_selection_accuracy: float
    argument_accuracy: float
    avg_latency_ms: float
    by_difficulty: Dict[str, Dict[str, int]]
    failures: List[EvalResult]


class EvalRunner:
    """Runs eval cases against the orchestrator."""
    
    def __init__(
        self,
        cases_path: Path,
        orchestrator_url: str = "localhost:50054",
        timeout_seconds: int = 30
    ):
        self.cases_path = cases_path
        self.orchestrator_url = orchestrator_url
        self.timeout_seconds = timeout_seconds
        self.results: List[EvalResult] = []
        
    def load_cases(
        self,
        suite: Optional[str] = None,
        difficulties: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Load eval cases from YAML file with optional filtering."""
        with open(self.cases_path) as f:
            data = yaml.safe_load(f)
        
        cases = data.get("cases", [])
        
        # Filter by difficulty
        if difficulties:
            cases = [c for c in cases if c.get("difficulty") in difficulties]
        
        # Filter by suite prefix (e.g., "ts_" for tool selection)
        if suite:
            prefix_map = {
                "tool_selection": "ts_",
                "argument_extraction": "ae_",
                "negative": "neg_",
                "edge": "edge_",
            }
            prefix = prefix_map.get(suite, suite)
            cases = [c for c in cases if c.get("id", "").startswith(prefix)]
        
        logger.info(f"Loaded {len(cases)} eval cases")
        return cases
    
    def run_single_case(self, case: Dict[str, Any]) -> EvalResult:
        """Run a single eval case."""
        case_id = case["id"]
        query = case["query"]
        expected_tools = case.get("expected_tools", [])
        expected_args = case.get("expected_arguments", {})
        should_use_tool = case.get("should_use_tool", len(expected_tools) > 0)
        
        logger.info(f"Running case {case_id}: {query[:50]}...")
        
        start_time = time.time()
        try:
            # Call orchestrator (mock for now)
            response = self._call_orchestrator(query)
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract tool calls from response
            actual_tools = self._extract_tools(response)
            actual_args = self._extract_arguments(response)
            
            # Check tool selection
            tool_selection_correct = self._check_tool_selection(
                expected_tools, actual_tools, should_use_tool
            )
            
            # Check arguments
            argument_correct = self._check_arguments(expected_args, actual_args)
            
            # Overall pass
            passed = tool_selection_correct and argument_correct
            
            return EvalResult(
                case_id=case_id,
                passed=passed,
                tool_selection_correct=tool_selection_correct,
                argument_correct=argument_correct,
                latency_ms=latency_ms,
                expected_tools=expected_tools,
                actual_tools=actual_tools,
                expected_args=expected_args,
                actual_args=actual_args,
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Case {case_id} failed with error: {e}")
            return EvalResult(
                case_id=case_id,
                passed=False,
                tool_selection_correct=False,
                argument_correct=False,
                latency_ms=latency_ms,
                expected_tools=expected_tools,
                actual_tools=[],
                expected_args=expected_args,
                actual_args={},
                error=str(e),
            )
    
    def _call_orchestrator(self, query: str) -> Dict[str, Any]:
        """Call the orchestrator with a query."""
        # For now, use mock response
        # In real implementation, use gRPC client:
        #
        # import grpc
        # from shared.generated import agent_pb2, agent_pb2_grpc
        # channel = grpc.insecure_channel(self.orchestrator_url)
        # stub = agent_pb2_grpc.AgentServiceStub(channel)
        # response = stub.Query(agent_pb2.QueryRequest(query=query))
        
        # Mock response for demonstration
        return {"tool_calls": [], "content": "Mock response"}
    
    def _extract_tools(self, response: Dict[str, Any]) -> List[str]:
        """Extract tool names from response."""
        tool_calls = response.get("tool_calls", [])
        if isinstance(tool_calls, list):
            return [tc.get("function", {}).get("name", tc.get("tool", "")) 
                    for tc in tool_calls if isinstance(tc, dict)]
        return []
    
    def _extract_arguments(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from response."""
        tool_calls = response.get("tool_calls", [])
        args = {}
        for tc in tool_calls:
            if isinstance(tc, dict):
                tool_name = tc.get("function", {}).get("name", tc.get("tool", ""))
                tool_args = tc.get("function", {}).get("arguments", tc.get("arguments", {}))
                if tool_name:
                    args[tool_name] = tool_args
        return args
    
    def _check_tool_selection(
        self,
        expected: List[str],
        actual: List[str],
        should_use_tool: bool
    ) -> bool:
        """Check if tool selection is correct."""
        if not should_use_tool:
            return len(actual) == 0
        
        if not expected:
            return True
        
        # For multi-tool cases, check if ANY expected tool was selected
        return len(set(expected) & set(actual)) > 0
    
    def _check_arguments(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any]
    ) -> bool:
        """Check if arguments are correct using glob patterns."""
        if not expected:
            return True
        
        for tool_name, expected_args in expected.items():
            if tool_name not in actual:
                continue  # Tool wasn't called, handled by tool_selection check
            
            actual_args = actual[tool_name]
            if not isinstance(actual_args, dict):
                return False
            
            for arg_name, expected_value in expected_args.items():
                if arg_name not in actual_args:
                    return False
                
                actual_value = str(actual_args[arg_name])
                expected_pattern = str(expected_value)
                
                # Support glob patterns with *
                if '*' in expected_pattern:
                    if not fnmatch.fnmatch(actual_value.lower(), expected_pattern.lower()):
                        return False
                else:
                    # Exact match (case insensitive)
                    if actual_value.lower() != expected_pattern.lower():
                        return False
        
        return True
    
    def run_all(
        self,
        suite: Optional[str] = None,
        difficulties: Optional[List[str]] = None
    ) -> EvalSummary:
        """Run all eval cases and return summary."""
        cases = self.load_cases(suite=suite, difficulties=difficulties)
        
        self.results = []
        for case in cases:
            result = self.run_single_case(case)
            self.results.append(result)
        
        return self._compute_summary(cases)
    
    def _compute_summary(self, cases: List[Dict]) -> EvalSummary:
        """Compute summary statistics."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        tool_correct = sum(1 for r in self.results if r.tool_selection_correct)
        arg_correct = sum(1 for r in self.results if r.argument_correct)
        
        latencies = [r.latency_ms for r in self.results]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        
        # Group by difficulty
        by_difficulty = {}
        for case, result in zip(cases, self.results):
            diff = case.get("difficulty", "unknown")
            if diff not in by_difficulty:
                by_difficulty[diff] = {"total": 0, "passed": 0}
            by_difficulty[diff]["total"] += 1
            if result.passed:
                by_difficulty[diff]["passed"] += 1
        
        failures = [r for r in self.results if not r.passed]
        
        return EvalSummary(
            total_cases=total,
            passed=passed,
            failed=failed,
            tool_selection_accuracy=tool_correct / total if total else 0,
            argument_accuracy=arg_correct / total if total else 0,
            avg_latency_ms=avg_latency,
            by_difficulty=by_difficulty,
            failures=failures,
        )
    
    def print_report(self, summary: EvalSummary) -> None:
        """Print formatted eval report."""
        print("\n" + "=" * 60)
        print("                    EVAL REPORT")
        print("=" * 60)
        
        print(f"\n📊 Overall Results:")
        print(f"   Total Cases:      {summary.total_cases}")
        print(f"   Passed:           {summary.passed} ({summary.passed/summary.total_cases*100:.1f}%)")
        print(f"   Failed:           {summary.failed}")
        
        print(f"\n📈 Metrics:")
        print(f"   Tool Selection:   {summary.tool_selection_accuracy*100:.1f}%")
        print(f"   Argument Correct: {summary.argument_accuracy*100:.1f}%")
        print(f"   Avg Latency:      {summary.avg_latency_ms:.1f}ms")
        
        print(f"\n📋 By Difficulty:")
        for diff, stats in summary.by_difficulty.items():
            pct = stats['passed'] / stats['total'] * 100 if stats['total'] else 0
            print(f"   {diff}: {stats['passed']}/{stats['total']} ({pct:.0f}%)")
        
        if summary.failures:
            print(f"\n❌ Failed Cases ({len(summary.failures)}):")
            for r in summary.failures[:5]:  # Show top 5 failures
                print(f"   - {r.case_id}: expected={r.expected_tools}, got={r.actual_tools}")
                if r.error:
                    print(f"     Error: {r.error}")
        
        print("\n" + "=" * 60)
        
        # Exit code based on thresholds
        passed_threshold = summary.tool_selection_accuracy >= 0.85
        print(f"\n{'✅ PASS' if passed_threshold else '❌ FAIL'}: Tool selection {'≥' if passed_threshold else '<'} 85% threshold")


def main():
    parser = argparse.ArgumentParser(description="Run evals for tool selection")
    parser.add_argument(
        "--suite",
        choices=["tool_selection", "argument_extraction", "negative", "edge", "all"],
        default="all",
        help="Which eval suite to run"
    )
    parser.add_argument(
        "--difficulty",
        help="Filter by difficulty (comma-separated: easy,medium,hard)"
    )
    parser.add_argument(
        "--cases-file",
        default="tests/evals/tool_selection_cases.yaml",
        help="Path to eval cases YAML file"
    )
    parser.add_argument(
        "--orchestrator-url",
        default="localhost:50054",
        help="Orchestrator gRPC address"
    )
    parser.add_argument(
        "--json-output",
        help="Write JSON results to file"
    )
    
    args = parser.parse_args()
    
    difficulties = args.difficulty.split(",") if args.difficulty else None
    suite = None if args.suite == "all" else args.suite
    
    # Find cases file
    cases_path = Path(args.cases_file)
    if not cases_path.exists():
        # Try relative to script
        cases_path = Path(__file__).parent / "tool_selection_cases.yaml"
    
    if not cases_path.exists():
        logger.error(f"Cases file not found: {cases_path}")
        sys.exit(1)
    
    runner = EvalRunner(
        cases_path=cases_path,
        orchestrator_url=args.orchestrator_url
    )
    
    summary = runner.run_all(suite=suite, difficulties=difficulties)
    runner.print_report(summary)
    
    # Write JSON output if requested
    if args.json_output:
        output = {
            "total_cases": summary.total_cases,
            "passed": summary.passed,
            "failed": summary.failed,
            "tool_selection_accuracy": summary.tool_selection_accuracy,
            "argument_accuracy": summary.argument_accuracy,
            "avg_latency_ms": summary.avg_latency_ms,
            "by_difficulty": summary.by_difficulty,
        }
        with open(args.json_output, 'w') as f:
            json.dump(output, f, indent=2)
        logger.info(f"Results written to {args.json_output}")
    
    # Exit with error if below threshold
    if summary.tool_selection_accuracy < 0.85:
        sys.exit(1)


if __name__ == "__main__":
    main()
