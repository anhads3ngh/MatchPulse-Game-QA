"""Regression tests for seeded synthetic analytics, triage, and simulation."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import engine
from main import route_api


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = engine.connect(Path(self.temp.name)/"test.db")
        engine.init(self.db)
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()


class DataTests(BaseTest):
    def test_sessions_seeded(self):
        self.assertGreater(self.db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],2500)
    def test_defects_seeded(self):
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM issues").fetchone()[0],104)
    def test_initial_runs_seeded(self):
        self.assertEqual(len(engine.recent_runs(self.db)),10)
    def test_repeatable_seed(self):
        a=engine.overview(self.db)
        engine.init(self.db,reset=True)
        b=engine.overview(self.db)
        self.assertEqual(a,b)
    def test_no_real_data(self):
        self.assertTrue(engine.overview(self.db)["meta"]["synthetic"])
        self.assertEqual(engine.overview(self.db)["meta"]["product"],"Stadium FC (fictional)")
    def test_date_ranges_restrict_sessions(self):
        self.assertLess(engine.overview(self.db,7)["kpis"]["sessions"],engine.overview(self.db,30)["kpis"]["sessions"])
    def test_platform_counts_partition_total(self):
        all_=engine.overview(self.db,30)["kpis"]["sessions"]
        partition=sum(engine.overview(self.db,30,p)["kpis"]["sessions"] for p in engine.PLATFORMS)
        self.assertEqual(all_,partition)
    def test_platform_subset_has_only_platform_sessions(self):
        a=engine.overview(self.db,14,"PC")
        self.assertTrue(all(x["name"]!="Xbox" or x["sessions"]==0 for x in a["platforms"]))
    def test_crash_rate_in_bounds(self):
        self.assertTrue(0<=engine.overview(self.db)["kpis"]["crash_rate"]<=100)
    def test_daily_series_length(self):
        self.assertEqual(len(engine.overview(self.db,14)["daily"]),14)
    def test_feature_data_covers_every_session(self):
        data=engine.overview(self.db,14)
        self.assertEqual(sum(x["sessions"] for x in data["features"]),data["kpis"]["sessions"])
    def test_risk_signals_transparent(self):
        self.assertTrue(all(x.get("evidence") for x in engine.overview(self.db)["signals"]))
    def test_invalid_range_rejected(self):
        with self.assertRaises(ValueError):engine.overview(self.db,365)
    def test_invalid_platform_rejected(self):
        with self.assertRaises(ValueError):engine.overview(self.db,7,"Switch")


class IssueTests(BaseTest):
    def test_search_by_title(self):
        self.assertTrue(engine.issues(self.db,search="replay"))
    def test_search_no_results(self):
        self.assertEqual(engine.issues(self.db,search="unfindable668388"),[])
    def test_severity_filter(self):
        self.assertTrue(all(x["severity"]=="Major" for x in engine.issues(self.db,severity="Major")))
    def test_status_filter(self):
        self.assertTrue(all(x["status"]=="Resolved" for x in engine.issues(self.db,status="Resolved")))
    def test_feature_filter(self):
        self.assertTrue(all(x["feature"]=="Career Mode" for x in engine.issues(self.db,feature="Career Mode")))
    def test_unknown_filter_rejected(self):
        with self.assertRaises(ValueError):engine.issues(self.db,severity="Ultra")
    def test_issue_detail_exists(self):
        self.assertEqual(engine.issue_detail(self.db,1)["id"],1)
    def test_issue_missing(self):
        self.assertIsNone(engine.issue_detail(self.db,9999))
    def test_issue_update_persisted_and_audited(self):
        engine.update_issue(self.db,1,"status","Ready to Verify")
        self.assertEqual(engine.issue_detail(self.db,1)["status"],"Ready to Verify")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit WHERE issue_id=1").fetchone()[0],1)
    def test_issue_invalid_patch_rejected(self):
        with self.assertRaises(ValueError):engine.update_issue(self.db,1,"title","injected")
    def test_similarity_ranks_template_duplicates(self):
        res=engine.issue_similarity(self.db,1)
        self.assertGreater(len(res),0)
        self.assertGreater(res[0]["similarity"],50)
        self.assertNotEqual(res[0]["id"],1)
    def test_similarity_is_sorted(self):
        results=engine.issue_similarity(self.db,1)
        self.assertEqual([x["similarity"] for x in results],sorted([x["similarity"] for x in results],reverse=True))
    def test_csv_contains_defects(self):
        out=engine.export_issues_csv(self.db)
        self.assertIn("id,title,feature,platform,severity,status",out)
        self.assertIn("Goal replay",out)


class SimulationTests(BaseTest):
    def test_run_added(self):
        old=len(engine.recent_runs(self.db))
        engine.generate_run(self.db,"Gameplay Smoke","PC",101)
        self.assertEqual(len(engine.recent_runs(self.db)),old+1)
    def test_same_seed_is_reproducible(self):
        a=engine.run_detail(self.db,engine.generate_run(self.db,"Full Regression","Xbox",170))
        b=engine.run_detail(self.db,engine.generate_run(self.db,"Full Regression","Xbox",170))
        expected=[(r["name"],r["outcome"],r["duration_ms"]) for r in a["results"]]
        actual=[(r["name"],r["outcome"],r["duration_ms"]) for r in b["results"]]
        self.assertEqual(expected,actual)
    def test_invalid_suite_rejected(self):
        with self.assertRaises(ValueError):engine.generate_run(self.db,"Do Everything","PC",100)
    def test_invalid_seed_rejected(self):
        with self.assertRaises(ValueError):engine.generate_run(self.db,"Gameplay Smoke","PC",-1)
    def test_result_count_is_consistent(self):
        run=engine.run_detail(self.db,engine.generate_run(self.db,"Full Regression","PC",100))
        self.assertEqual(run["passed"]+run["failed"],len(run["results"]))
        self.assertEqual(len(run["results"]),30)
    def test_small_suite_has_10_cases(self):
        run=engine.run_detail(self.db,engine.generate_run(self.db,"Gameplay Smoke","PC",100))
        self.assertEqual(len(run["results"]),10)
    def test_report_contains_disclosure(self):
        report=engine.release_report(self.db)
        self.assertIn("synthetic qa data",report.lower())
        self.assertIn("Critical",report)
        self.assertIn("Recommended next actions",report)


class APITests(BaseTest):
    def test_health(self):
        status,data=route_api(self.db,"GET","/api/health")
        self.assertEqual(status,200)
        self.assertTrue(data["ok"])
    def test_config(self):
        status,data=route_api(self.db,"GET","/api/config")
        self.assertEqual(status,200)
        self.assertIn("Full Regression",data["suites"])
    def test_fetch_issues(self):
        status,data=route_api(self.db,"GET","/api/issues",{"severity":["Major"]})
        self.assertEqual(status,200)
        self.assertTrue(all(i["severity"]=="Major" for i in data["issues"]))
    def test_issue_detail_includes_duplicate_candidates(self):
        status,data=route_api(self.db,"GET","/api/issues/1")
        self.assertEqual(status,200)
        self.assertIn("similar",data)
    def test_create_run(self):
        status,data=route_api(self.db,"POST","/api/runs",payload={"suite":"Gameplay Smoke","platform":"PC","seed":55})
        self.assertEqual(status,201)
        self.assertEqual(len(data["results"]),10)
    def test_patch_issue(self):
        status,data=route_api(self.db,"PATCH","/api/issues/1",payload={"field":"owner","value":"A. Singh"})
        self.assertEqual(status,200)
        self.assertEqual(data["owner"],"A. Singh")
    def test_unknown_endpoint(self):
        self.assertEqual(route_api(self.db,"GET","/api/not-real")[0],404)
    def test_invalid_run_data(self):
        with self.assertRaises(ValueError):route_api(self.db,"POST","/api/runs",payload={"suite":"Unknown","platform":"PC","seed":55})
    def test_report_route(self):
        status,report=route_api(self.db,"GET","/api/report.md")
        self.assertEqual(status,200)
        self.assertIn("QUALITY RELEASE BRIEF",report)


if __name__=="__main__":unittest.main()
