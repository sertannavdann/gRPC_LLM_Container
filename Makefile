# gRPC_llm (pruned): actions library + a client for the llm-tiers runtime.
.PHONY: help test llm-up llm-down llm-status llm-logs llm-bench llm-stability
LLM_TIERS_DIR := ../llm-tiers
LLM_TIERS ?= standard-mlx
TIER ?= standard-mlx
help:
	@echo "make test                       unit + sandbox tests (python3 with requests, grpcio, pytest)"
	@echo "make llm-up|llm-down|llm-status|llm-logs|llm-bench|llm-stability TIER=   delegate to ../llm-tiers"
test:
	@python3 -m pytest tests -q
llm-up llm-down llm-status llm-logs llm-bench llm-stability:
	@$(MAKE) --no-print-directory -C $(LLM_TIERS_DIR) $(subst llm-,,$@) LLM_TIERS="$(LLM_TIERS)" TIER=$(TIER)
