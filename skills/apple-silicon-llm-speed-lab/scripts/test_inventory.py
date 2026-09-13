"""Pure parser checks; host detection itself is tested only on the actual host."""
import json
import unittest

import inventory


class InventoryTests(unittest.TestCase):
    def test_mac_gpu_whitelist_excludes_serials_nested_displays(self):
        raw = {"SPDisplaysDataType": [{"sppci_model": "Synthetic Apple GPU", "sppci_cores": "8",
                                      "serial_number": "PRIVATE", "spdisplays_ndrvs": [{"serial": "PRIVATE"}]}]}
        result = inventory.mac_gpu_records(json.dumps(raw))
        self.assertEqual(result, [{"sppci_model": "Synthetic Apple GPU", "sppci_cores": "8"}])
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_linux_memory_converts_only_known_kib_fields(self):
        result = inventory.linux_memory("MemTotal: 100 kB\nMemAvailable: 20 kB\nSecret: 3 kB\nSwapFree: 4 kB\n")
        self.assertEqual(result, {"MemTotal": 102400, "MemAvailable": 20480, "SwapFree": 4096})

    def test_nvidia_memory_and_driver_no_uuid(self):
        result = inventory.nvidia_records('"GPU, model", 24000, 12000, 123.4\n')
        self.assertEqual(result[0]["name"], "GPU, model")
        self.assertEqual(result[0]["memory_total_mib"], 24000)
        self.assertIsNone(inventory.number("N/A"))

    def test_windows_only_selected_fields_exported(self):
        raw = {"cpu": ["CPU"], "memory_bytes": 1024, "serial": "PRIVATE",
               "gpus": {"Name": "GPU", "AdapterRAM": 512, "DriverVersion": "1", "PNPDeviceID": "PRIVATE"}}
        result = inventory.windows_records(json.dumps(raw))
        self.assertEqual(result["memory_bytes"], 1024)
        self.assertNotIn("PRIVATE", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
