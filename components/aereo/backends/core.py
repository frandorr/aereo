"""Task runner for resolving and executing single extraction tasks."""

from __future__ import annotations

from typing import Any, Mapping

from aereo.interfaces import ExtractionTask, merge_params
from aereo.registry import AereoRegistry
from aereo.schemas import ArtifactSchema
from pandera.typing.geopandas import GeoDataFrame
from structlog import get_logger

logger = get_logger()


class TaskRunner:
    """Resolves the correct extractor plugin and executes a single extraction task.

    Resolution follows a three-tier priority:

    1. ``task.task_context["extractor_hint"]``
    2. ``task.profile.plugin_hints["extract"]``
    3. Auto-discover from ``task.profile.collections``
    """

    def __init__(
        self,
        registry: AereoRegistry,
        init_params: Mapping[str, Any] | None = None,
    ) -> None:
        """Create a new TaskRunner.

        Args:
            registry: Plugin registry used to look up extractors.
            init_params: Optional default parameters passed to every extractor
                constructor.
        """
        self.registry = registry
        self._init_params = dict(init_params or {})

    def run(self, task: ExtractionTask) -> GeoDataFrame[ArtifactSchema]:
        """Resolve the extractor for *task* and run it.

        Args:
            task: The extraction task to execute.

        Returns:
            A ``GeoDataFrame[ArtifactSchema]`` containing the extracted artifacts.

        Raises:
            ValueError: If no extractor plugin can be resolved for the task's
                profile.
        """
        task_init = dict(self._init_params)
        task_init.update(task.task_context.get("init_params", {}))

        hint = task.task_context.get("extractor_hint")
        if hint and self.registry.has_extractor(hint):
            extractor = self.registry.get_extractor(hint, **task_init)
        else:
            profile_hint = task.profile.plugin_hints.get("extract")
            if profile_hint and self.registry.has_extractor(profile_hint):
                extractor = self.registry.get_extractor(profile_hint, **task_init)
            else:
                plugin_name: str | None = None
                for collection in task.profile.collections:
                    plugin_names = self.registry.find_extractors_for(collection)
                    if plugin_names:
                        plugin_name = plugin_names[0]
                        break
                if plugin_name is None:
                    raise ValueError(
                        f"No extractor plugin found for profile: {task.profile.name}"
                    )
                extractor = self.registry.get_extractor(plugin_name, **task_init)

        effective_params = merge_params(None, task.profile.extract_params)
        return extractor.extract(task, effective_params)
