"""Verify release selection fails closed before any Cloud mutation."""

import copy
import unittest

from deploy_frappe_cloud import SITE, plan

SHA = "a" * 40


def deployment_info():
	return {
		"apps": [
			{
				"app": "crm",
				"source": "crm-source",
				"repository_owner": "SudoStudy",
				"repository": "crm",
				"branch": "main",
				"current_hash": "b" * 40,
				"current_release": "old-crm",
				"releases": [{"name": "tested-crm", "hash": SHA}],
			},
			{
				"app": "frappe",
				"source": "frappe-source",
				"current_hash": "c" * 40,
				"current_release": "deployed-framework",
				"releases": [{"name": "new-framework", "hash": "d" * 40}],
			},
		],
		"sites": [{"name": SITE, "bench": "existing", "server": "existing", "skip_backups": True}],
	}


def baseline():
	return [
		{"app": a["app"], "source": a["source"], "hash": a["current_hash"]} for a in deployment_info()["apps"]
	]


class ReleasePlanTests(unittest.TestCase):
	def test_exact_crm_preserves_sibling_and_requires_backup(self):
		info = deployment_info()
		before = copy.deepcopy(info)
		apps, sites = plan(info, SHA, baseline())
		self.assertEqual(apps[0]["release"], "tested-crm")
		self.assertEqual(apps[1]["release"], "deployed-framework")
		self.assertEqual(apps[1]["hash"], "c" * 40)
		self.assertFalse(sites[0]["skip_backups"])
		self.assertFalse(sites[0]["skip_failing_patches"])
		self.assertEqual(info, before)

	def test_refuses_pending_removal_or_source_change(self):
		info = deployment_info()
		info["removed_apps"] = [{"app": "builder"}]
		with self.assertRaises(RuntimeError):
			plan(info, SHA, baseline())
		info = deployment_info()
		info["apps"][1]["source"] = "another-repository"
		with self.assertRaises(RuntimeError):
			plan(info, SHA, baseline())

	def test_refuses_missing_exact_revision(self):
		info = deployment_info()
		info["apps"][0]["releases"] = []
		with self.assertRaises(RuntimeError):
			plan(info, SHA, baseline())

	def test_refuses_different_source_or_branch(self):
		for key, value in [("repository_owner", "frappe"), ("branch", "develop")]:
			with self.subTest(key=key):
				info = deployment_info()
				info["apps"][0][key] = value
				with self.assertRaises(RuntimeError):
					plan(info, SHA, baseline())

	def test_refuses_additional_sites_or_active_deploy(self):
		info = deployment_info()
		info["sites"].append({"name": "another-site"})
		with self.assertRaises(RuntimeError):
			plan(info, SHA, baseline())
		for flag in ["deploy_in_progress", "has_running_release_pipeline", "bench_creation_underway"]:
			with self.subTest(flag=flag):
				info = deployment_info()
				info[flag] = True
				with self.assertRaises(RuntimeError):
					plan(info, SHA, baseline())


if __name__ == "__main__":
	unittest.main()
