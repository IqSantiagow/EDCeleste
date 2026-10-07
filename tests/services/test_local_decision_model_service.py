import functools
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from edceleste.services import local_decision_model_service
from edceleste.services.decision_model_download_service import (
    DecisionModelDownloadService,
)
from edceleste.services.local_decision_model_service import (
    LocalDecisionModelService,
    ModelNotDownloaded,
    switch_qwen_kernels_to_device,
)

MODULE = "edceleste.services.local_decision_model_service"


class LocalDecisionModelServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.download_service = MagicMock(spec=DecisionModelDownloadService)
        self.download_service.model_folder = Path("C:/models/decider")
        self.download_service.is_model_downloaded.return_value = True
        self.service = LocalDecisionModelService(self.download_service)

    def load_with_fake_decider(self, cuda_available: bool = True, triton=True):
        fake_decider_module = MagicMock()
        fake_torch = MagicMock()
        fake_torch.cuda.is_available.return_value = cuda_available
        with (
            patch.dict(
                sys.modules,
                {
                    "torch": fake_torch,
                    "decider": MagicMock(),
                    "decider.infer": fake_decider_module,
                },
            ),
            patch(f"{MODULE}.switch_qwen_kernels_to_device") as switch_kernels_mock,
            patch(
                f"{MODULE}.importlib.util.find_spec",
                return_value=MagicMock() if triton else None,
            ),
        ):
            self.service.load_model()
        return fake_decider_module.Decider, switch_kernels_mock

    def test_load_model_reads_the_downloaded_folder_on_the_gpu(self):
        decider_class, switch_kernels_mock = self.load_with_fake_decider()

        decider_class.assert_called_once_with(
            str(self.download_service.model_folder), device="cuda"
        )
        switch_kernels_mock.assert_called_once_with("cuda")

    def test_load_model_auto_falls_back_to_cpu_without_a_gpu(self):
        decider_class, _ = self.load_with_fake_decider(cuda_available=False)

        self.assertEqual(decider_class.call_args.kwargs["device"], "cpu")

    def test_load_model_uses_the_chosen_device(self):
        self.service.change_device("cpu")

        decider_class, switch_kernels_mock = self.load_with_fake_decider()

        self.assertEqual(decider_class.call_args.kwargs["device"], "cpu")
        switch_kernels_mock.assert_called_once_with("cpu")

    def test_load_model_runs_eager_forward_without_triton(self):
        decider_class, _ = self.load_with_fake_decider(triton=False)

        engine = decider_class.return_value.eng
        self.assertIs(engine._fwd_impl, engine._fwd_eager)

    def test_load_model_refuses_a_model_that_is_not_downloaded(self):
        self.download_service.is_model_downloaded.return_value = False

        with self.assertRaises(ModelNotDownloaded):
            self.service.load_model()

    def test_change_device_unloads_the_model(self):
        self.service.decider = MagicMock()

        with patch.dict(sys.modules, {"torch": MagicMock()}):
            self.service.change_device("cpu")

        self.assertIsNone(self.service.decider)

    def test_running_device_is_none_before_loading(self):
        self.assertIsNone(self.service.running_device())

    def test_running_device_reports_where_the_model_runs(self):
        self.service.decider = MagicMock(dev="cuda")

        self.assertEqual(self.service.running_device(), "cuda")

    def test_warm_up_asks_one_question_so_the_first_command_is_fast(self):
        self.service.ask = MagicMock(return_value={"warm_up": {"noul": 0.9}})

        self.service.warm_up()

        self.service.ask.assert_called_once()

    def test_unload_model_frees_the_model(self):
        self.service.decider = MagicMock()

        with patch.dict(sys.modules, {"torch": MagicMock()}):
            self.service.unload_model()

        self.assertIsNone(self.service.decider)


class SwitchQwenKernelsToDeviceTest(unittest.TestCase):
    def setUp(self):
        def torch_chunk_gated_delta_rule():
            return "torch"

        @functools.wraps(torch_chunk_gated_delta_rule)
        def fast_chunk_gated_delta_rule():
            return "gpu"

        def torch_recurrent_gated_delta_rule():
            return "torch"

        @functools.wraps(torch_recurrent_gated_delta_rule)
        def fast_recurrent_gated_delta_rule():
            return "gpu"

        self.qwen_module = SimpleNamespace(
            torch_chunk_gated_delta_rule=fast_chunk_gated_delta_rule,
            torch_recurrent_gated_delta_rule=fast_recurrent_gated_delta_rule,
        )
        modules_patcher = patch.dict(
            sys.modules,
            {
                "transformers.models.qwen3_5": SimpleNamespace(
                    modeling_qwen3_5=self.qwen_module
                ),
            },
        )
        modules_patcher.start()
        self.addCleanup(modules_patcher.stop)
        kernels_patcher = patch.dict(
            local_decision_model_service.gpu_kernels, clear=True
        )
        kernels_patcher.start()
        self.addCleanup(kernels_patcher.stop)

    def test_cpu_gets_the_plain_torch_functions(self):
        switch_qwen_kernels_to_device("cpu")

        self.assertEqual(self.qwen_module.torch_chunk_gated_delta_rule(), "torch")
        self.assertEqual(self.qwen_module.torch_recurrent_gated_delta_rule(), "torch")

    def test_cuda_gets_the_gpu_kernels_back_after_cpu(self):
        switch_qwen_kernels_to_device("cpu")

        switch_qwen_kernels_to_device("cuda")

        self.assertEqual(self.qwen_module.torch_chunk_gated_delta_rule(), "gpu")
        self.assertEqual(self.qwen_module.torch_recurrent_gated_delta_rule(), "gpu")
