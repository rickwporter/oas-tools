# the first target is the default, so just run help
help: ## This message
	@echo "===================="
	@echo " Available Commands"
	@echo "===================="
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m\033[0m\n"} /^[$$()% a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

LAYOUT_FILE := layout.yaml
OPENAPI_SPEC := pet.yaml
PROJECT_DIRECTORY := .
PACKAGE_NAME := pets_cli

TEST_TARGET ?= tests
poetry_run ?= poetry run

###########
##@ General
default: help

wheel: ## Build the wheel package that is installable
	poetry build

install: ## Install the package
	poetry install

all: install gen lint cov ## Perform a full cycle
	$(poetry_run) pets

###########
##@ Code generation
layout-lint:  ## Check the layout file format
	$(poetry_run) cli-gen layout check $(LAYOUT_FILE)

gen: layout-lint ## Generate CLI code
	$(poetry_run) cli-gen generate $(LAYOUT_FILE) $(OPENAPI_SPEC) $(PACKAGE_NAME) --project-dir $(PROJECT_DIRECTORY)

missing: ## Print the OAS operations not in the layout
	$(poetry_run) cli-gen unreferenced $(LAYOUT_FILE) $(OPENAPI_SPEC)

###########
##@ Linting
lint: ## Check code formatting
	$(poetry_run) ruff check

delint: ## Fix formatting issues
	$(poetry_run) ruff check --fix


###########
##@ Test
test: ## Run unit tests
	$(poetry_run) pytest -v $(TEST_TARGET)

cov: ## Run unit tests with code coverage measurments
	$(poetry_run) coverage run -m pytest -v $(TEST_TARGET)
	$(poetry_run) coverage report -m
	$(poetry_run) coverage html
