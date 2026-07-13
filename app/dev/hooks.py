from app.dev.analyze import analyze_with_trace
from app.dev.store import record_trace
from app.services import webhook_processor_service


def register_dev_hooks() -> None:
    async def recorder(debug, metadata) -> None:
        record_trace(debug, metadata)

    async def analyze_and_record(analyzer, email_input, metadata):
        debug = await analyze_with_trace(analyzer, email_input)
        await recorder(debug, metadata)
        return debug.result

    webhook_processor_service.set_dev_analyze(analyze_and_record)
