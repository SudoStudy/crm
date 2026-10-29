"""Deploy tested CRM main to its existing Cloud site, preserving sibling apps."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

CLOUD = "https://cloud.frappe.io/api/method/"
TEAM = "dhg7aotrva"
GROUP = "bench-47516"
SITE = "crm-tdu-mvn.z.frappe.cloud"
REPO = "SudoStudy/crm"


def request(url, headers, payload=None):
	data = json.dumps(payload).encode() if payload is not None else None
	req = urllib.request.Request(
		url, data=data, headers={"User-Agent": "SudoStudy-CRM-Deployment/1.0", **headers}
	)
	try:
		with urllib.request.urlopen(req, timeout=60) as response:
			return json.load(response)
	except (urllib.error.URLError, ValueError):
		# Responses can contain credentials or provider tracebacks. Never log them.
		raise RuntimeError("API request failed; inspect the provider dashboard before retrying.") from None


def cloud(method, **payload):
	result = request(
		CLOUD + method,
		{
			"Authorization": f"token {os.environ['FRAPPE_CLOUD_API_KEY']}:{os.environ['FRAPPE_CLOUD_API_SECRET']}",
			"X-Press-Team": TEAM,
			"Content-Type": "application/json",
		},
		payload,
	)
	if result.get("exc_type") or result.get("exception"):
		raise RuntimeError("Cloud rejected the request; inspect its dashboard before retrying.")
	return result.get("message")


def assert_current_main(sha):
	result = request(
		f"https://api.github.com/repos/{REPO}/git/ref/heads/main",
		{"Authorization": f"Bearer {os.environ['GH_TOKEN']}", "Accept": "application/vnd.github+json"},
	)
	if result["object"]["sha"] != sha:
		raise RuntimeError("A newer main commit exists. Deploy its tested run instead.")


def app_hashes(apps, field="current_hash"):
	return {app["app"]: app[field] for app in apps}


def plan(info, sha, baseline):
	if info.get("removed_apps"):
		raise RuntimeError("The group has pending app removals; review before deploying.")
	if {app["app"] for app in info["apps"]} != {app["app"] for app in baseline}:
		raise RuntimeError("The group app membership differs from the deployed bench.")
	for app in info["apps"]:
		deployed = next(row for row in baseline if row["app"] == app["app"])
		if (
			app.get("will_branch_change")
			or app["source"] != deployed["source"]
			or app["current_hash"] != deployed["hash"]
		):
			raise RuntimeError("App source or revision differs from the site bench; review before deploying.")
	if any(
		info.get(flag)
		for flag in ("deploy_in_progress", "has_running_release_pipeline", "bench_creation_underway")
	):
		raise RuntimeError("Cloud already has a deployment in progress.")
	apps = info["apps"]
	crm = [app for app in apps if app["app"] == "crm"]
	if (
		len(crm) != 1
		or crm[0]["repository_owner"] != "SudoStudy"
		or crm[0]["repository"] != "crm"
		or crm[0]["branch"] != "main"
	):
		raise RuntimeError("Cloud CRM source differs from SudoStudy/crm main.")
	if {site["name"] for site in info["sites"]} != {SITE}:
		raise RuntimeError("Cloud group site membership changed; review before deploying.")
	selected = []
	for app in apps:
		release, commit = app["current_release"], app["current_hash"]
		if app["app"] == "crm":
			matching = [release for release in app["releases"] if release["hash"] == sha]
			if commit != sha:
				if len(matching) != 1:
					raise RuntimeError("The exact tested CRM commit is not available in Cloud.")
				release, commit = matching[0]["name"], sha
		if not release or not commit:
			raise RuntimeError("A sibling app lacks a pinned deployed release.")
		selected.append({"app": app["app"], "source": app["source"], "release": release, "hash": commit})
	sites = [{**site, "skip_backups": False, "skip_failing_patches": False} for site in info["sites"]]
	return selected, sites


def main():
	for variable in ("GH_TOKEN", "FRAPPE_CLOUD_API_KEY", "FRAPPE_CLOUD_API_SECRET", "DEPLOY_SHA"):
		if not os.environ.get(variable):
			raise RuntimeError(f"Missing {variable}; configure production deployment secrets first.")
	sha = os.environ["DEPLOY_SHA"]
	if not re.fullmatch(r"[0-9a-f]{40}", sha):
		raise RuntimeError("Expected a full tested commit SHA.")
	assert_current_main(sha)
	group = cloud("press.api.client.get", doctype="Release Group", name=GROUP)
	if any(app.get("enable_auto_deploy") for app in group["apps"]):
		raise RuntimeError("Disable parallel Cloud auto-deploy before using the checked GitHub deployment.")
	initial = cloud("press.api.bench.deploy_information", name=GROUP)
	installed = cloud("press.api.site.installed_apps", name=SITE)
	before_site = app_hashes(installed, "hash")
	if len(initial["sites"]) != 1 or initial["sites"][0]["name"] != SITE:
		raise RuntimeError("Expected only the approved CRM site in the Cloud group.")
	baseline = cloud("press.api.bench.get_installed_apps_in_version", name=initial["sites"][0]["bench"])
	if before_site.get("crm") == sha:
		print("The live CRM site already runs the tested commit.")
		return
	# Fetch metadata only; all auto-deploy switches were checked above.
	cloud("press.api.bench.fetch_latest_app_update", name=GROUP, app="crm")
	for _ in range(30):
		info = cloud("press.api.bench.deploy_information", name=GROUP)
		if any(
			release["hash"] == sha
			for app in info["apps"]
			if app["app"] == "crm"
			for release in app["releases"]
		):
			break
		time.sleep(10)
	if app_hashes(initial["apps"]) != app_hashes(info["apps"]):
		raise RuntimeError("The deployed app versions changed while preparing this release.")
	apps, sites = plan(info, sha, baseline)
	assert_current_main(sha)
	# Never retry this mutation automatically: a timeout has an unknown outcome.
	cloud("press.api.bench.deploy_and_update", name=GROUP, apps=apps, sites=sites, run_will_fail_check=True)
	print(f"Cloud accepted CRM {sha}; waiting for the actual site update with backups enabled.")
	expected = {**before_site, "crm": sha}
	for _ in range(180):
		time.sleep(20)
		actual = app_hashes(cloud("press.api.site.installed_apps", name=SITE), "hash")
		if actual == expected:
			final = cloud("press.api.bench.deploy_information", name=GROUP)
			if app_hashes(final["apps"]) != app_hashes(apps, "hash"):
				raise RuntimeError("Site updated, but sibling bench app versions differ; inspect Cloud.")
			with urllib.request.urlopen(
				urllib.request.Request(
					"https://sales.sudostudy.com/crm", headers={"User-Agent": "SudoStudy-CRM-Deployment/1.0"}
				),
				timeout=30,
			) as response:
				if response.status != 200:
					raise RuntimeError("The CRM page did not return success.")
			print(f"Verified live CRM {sha}, sibling apps preserved, CRM page available.")
			return
	raise RuntimeError("Live version was not verified within one hour. Inspect Cloud before any retry.")


if __name__ == "__main__":
	try:
		main()
	except RuntimeError as error:
		print(str(error), file=sys.stderr)
		sys.exit(1)
