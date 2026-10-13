"""Live extraction steps saved on the job while sources are read.

Every source, part and step here is SYNTHETIC test data; no network call runs.
"""

from bharat_sourcer.extraction import ExtractionError
from bharat_sourcer.intake import extract_sources
from bharat_sourcer.jobs import JobService
from bharat_sourcer.reconcile import ReconcileDraft
from bharat_sourcer.schemas import BomItem, CreateJob, Evidence

VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"
PAGE = "https://www.instructables.com/Synthetic/"


def line(name):
    return BomItem(
        line_id="L01",
        raw_name=name,
        evidence=[Evidence(timestamp="00:10", observation=f"Synthetic video shows {name}")],
    )


def test_intake_reports_each_source_as_it_finishes():
    steps = []

    class Extractor:
        def extract(self, url):
            if url == PAGE:
                raise ExtractionError("SOURCE_UNAVAILABLE", "The project page could not be fetched")
            return [line("ESP32 board"), line("BME280 sensor")]

    extract_sources(Extractor(), [VIDEO, PAGE], lambda *step: steps.append(step))
    video, page = f"source:{VIDEO}", f"source:{PAGE}"
    assert (video, "running", "Reading the video", None) in steps
    assert (video, "done", None, "2 parts found") in steps
    assert (page, "running", "Reading instructables.com", None) in steps
    assert (page, "failed", None, "The project page could not be fetched") in steps


class Reconciler:
    def review(self, items, project):
        return ReconcileDraft()


class Filler:
    def fill(self, items, project):
        return {}


def test_job_saves_steps_in_order_with_times():
    class Extractor:
        def extract(self, url):
            return [line("ESP32 board"), line("BME280 sensor")]

    service = JobService(
        Extractor(), "synthetic-model", reconciler=Reconciler(), spec_filler=Filler()
    )
    job, token = service.create(CreateJob(url=VIDEO))
    service.extract(job.job_id)
    job = service.get(job.job_id, token)
    assert [(s.key, s.status) for s in job.extraction_progress] == [
        ("reconcile", "done"),
        ("spec_fill", "done"),
        (f"source:{VIDEO}", "done"),
    ]
    source = job.extraction_progress[2]
    assert source.detail == "2 parts found" and source.started_at and source.finished_at


def test_demo_jobs_have_no_steps():
    service = JobService()
    job, token = service.create(CreateJob(url=VIDEO))
    service.extract(job.job_id)
    assert service.get(job.job_id, token).extraction_progress == []
