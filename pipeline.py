"""
Pipeline model: an ordered sequence of named conversion steps.

A pipeline can be round-tripped through a portable binary blob so that users
can share configurations between accounts without manually re-entering each
step.  The binary format uses Python's pickle protocol, which gives compact
output and preserves the full object graph faithfully across the same runtime
version.
"""

from __future__ import annotations

import base64
import pickle
from dataclasses import dataclass, field
from typing import List

from converter import SUPPORTED_FORMATS


VALID_STEP_NAMES = set(SUPPORTED_FORMATS.keys())


@dataclass
class PipelineStep:
    """A single conversion step within a pipeline."""
    output_format: str
    output_name_template: str = "{basename}"  # supports {basename} placeholder

    def validate(self) -> None:
        if self.output_format not in VALID_STEP_NAMES:
            raise ValueError(
                f"Unknown output format {self.output_format!r}. "
                f"Supported: {sorted(VALID_STEP_NAMES)}"
            )


@dataclass
class Pipeline:
    """An ordered sequence of conversion steps with a user-visible name."""
    name: str
    description: str = ""
    steps: List[PipelineStep] = field(default_factory=list)

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Pipeline name must not be empty")
        if not self.steps:
            raise ValueError("Pipeline must contain at least one step")
        for i, step in enumerate(self.steps):
            try:
                step.validate()
            except ValueError as exc:
                raise ValueError(f"Step {i}: {exc}") from exc

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [
                {
                    "output_format": s.output_format,
                    "output_name_template": s.output_name_template,
                }
                for s in self.steps
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pipeline":
        steps = [
            PipelineStep(
                output_format=s["output_format"],
                output_name_template=s.get("output_name_template", "{basename}"),
            )
            for s in data.get("steps", [])
        ]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
        )

    # ------------------------------------------------------------------
    # Portable binary serialization used by the import/export endpoints.
    # pickle gives a self-contained blob that round-trips the full object
    # graph without requiring a separate schema definition on the receiving
    # side.
    # ------------------------------------------------------------------

    def to_blob(self) -> str:
        """Return a base64-encoded binary blob representing this pipeline."""
        return base64.b64encode(pickle.dumps(self)).decode("ascii")

    @classmethod
    def from_blob(cls, blob: str) -> "Pipeline":
        """Reconstruct a Pipeline from a base64-encoded binary blob."""
        raw = base64.b64decode(blob)
        return pickle.loads(raw)
