import asyncio
import unittest
from unittest.mock import patch

from fastapi import FastAPI

from ai_receptionist.web import app, get_local_pipeline, lifespan


class ProviderLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_application_start_does_not_load_unused_local_models(self):
        test_app = FastAPI()
        with patch("ai_receptionist.web.LocalVoicePipeline") as local_pipeline:
            async with lifespan(test_app):
                self.assertIsNone(test_app.state.pipeline)
                local_pipeline.assert_not_called()
            local_pipeline.assert_not_called()

    async def test_local_provider_is_loaded_once_on_first_request(self):
        app.state.pipeline = None
        app.state.pipeline_lock = asyncio.Lock()
        pipeline = object()
        try:
            with (
                patch("ai_receptionist.web.LocalVoicePipeline", return_value=pipeline) as factory,
                patch("ai_receptionist.web.Settings.from_environment", return_value=object()),
            ):
                first, second = await asyncio.gather(
                    get_local_pipeline(), get_local_pipeline()
                )
            self.assertIs(first, pipeline)
            self.assertIs(second, pipeline)
            factory.assert_called_once()
        finally:
            app.state.pipeline = None


if __name__ == "__main__":
    unittest.main()
