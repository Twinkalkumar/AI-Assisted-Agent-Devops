from abc import ABC, abstractmethod


class Tool(ABC):
    """Base class for anything the agent can call.

    Subclass this to add a new capability (e.g. a Kubernetes-specific
    helper, a GitHub API call, a Terraform runner). The agent discovers
    tools purely through `name`/`description`/`parameters`, so the LLM
    prompt never needs hand-written per-tool glue.
    """

    name: str
    description: str
    # JSON-schema-style dict describing the `args` object passed to run().
    parameters: dict

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the tool and return a string result shown back to the LLM."""
        raise NotImplementedError

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
