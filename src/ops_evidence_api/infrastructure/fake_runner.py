import asyncio
import logging
from pathlib import Path

from pydantic import ValidationError

from ops_evidence_api.application.models import OutboxMessage
from ops_evidence_api.application.ports import FakeRunnerStore
from ops_evidence_api.contracts.api import AnalysisResult

logger = logging.getLogger(__name__)


class FakeRunnerError(Exception):
    def __init__(self, code: str, detail: str, *, retryable: bool) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.retryable = retryable


class FixtureAnalysisRunner:
    """Loads deterministic results for synthetic demo scenarios only."""

    def __init__(self, fixture_root: Path) -> None:
        self._fixture_root = fixture_root

    async def run(self, message: OutboxMessage) -> dict[str, object]:
        scenario_id = message.payload.get("scenarioId")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise FakeRunnerError(
                "UNSUPPORTED_SCENARIO",
                "Fake analysis requires a bundled scenarioId.",
                retryable=False,
            )

        result_path = self._fixture_root / scenario_id / "expected-analysis.json"
        try:
            raw_result = await asyncio.to_thread(result_path.read_text, encoding="utf-8")
        except FileNotFoundError as exc:
            raise FakeRunnerError(
                "UNSUPPORTED_SCENARIO",
                f"No bundled result exists for scenario '{scenario_id}'.",
                retryable=False,
            ) from exc
        except OSError as exc:
            raise FakeRunnerError(
                "FIXTURE_READ_FAILED",
                "The bundled analysis result could not be read.",
                retryable=True,
            ) from exc

        try:
            result = AnalysisResult.model_validate_json(raw_result)
        except ValidationError as exc:
            raise FakeRunnerError(
                "INVALID_FIXTURE_RESULT",
                "The bundled analysis result does not match the result contract.",
                retryable=False,
            ) from exc
        return result.model_dump(mode="json", by_alias=True)


class FakeOutboxRelay:
    """Single-process development adapter that drains requested events from the outbox."""

    def __init__(
        self,
        store: FakeRunnerStore,
        runner: FixtureAnalysisRunner,
        *,
        poll_interval_seconds: float,
        analysis_delay_seconds: float,
    ) -> None:
        self._store = store
        self._runner = runner
        self._poll_interval_seconds = poll_interval_seconds
        self._analysis_delay_seconds = analysis_delay_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("Fake outbox relay is already running.")
        self._task = asyncio.create_task(self._run(), name="fake-outbox-relay")

    async def close(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                message = await self._store.claim_next_fake_message()
                if message is None:
                    await self._wait_for_next_poll()
                    continue
                if self._analysis_delay_seconds:
                    await asyncio.sleep(self._analysis_delay_seconds)
                await self._process(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected fake outbox relay failure")
                await self._wait_for_next_poll()

    async def _process(self, message: OutboxMessage) -> None:
        try:
            result = await self._runner.run(message)
        except FakeRunnerError as exc:
            await self._store.fail_fake_message(
                message,
                code=exc.code,
                detail=exc.detail,
                retryable=exc.retryable,
            )
        except Exception:
            logger.exception(
                "Unexpected fake analysis failure", extra={"event_id": message.event_id}
            )
            await self._store.fail_fake_message(
                message,
                code="FAKE_RUNNER_FAILED",
                detail="The local fake runner failed unexpectedly.",
                retryable=True,
            )
        else:
            await self._store.complete_fake_message(message, result)

    async def _wait_for_next_poll(self) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=self._poll_interval_seconds)
        except TimeoutError:
            pass
