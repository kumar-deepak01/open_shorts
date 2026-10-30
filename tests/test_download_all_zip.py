"""``/api/jobs/{id}/download-all`` builds one ZIP per request.

Two downloads of the same job in the same second used to share
``clips_<epoch>.zip``: the second truncated the file the first was streaming,
and the first cleanup deleted it from under the second."""
import asyncio
import json
import os
import zipfile

import app


async def _no_files(job_id, request):
    return True


def _make_job(tmp_path, job_id):
    out = tmp_path / job_id
    out.mkdir()
    (out / "video_metadata.json").write_text(json.dumps(
        {"shorts": [{"video_url": f"/videos/{job_id}/clip_a.mp4"},
                    {"video_url": f"/videos/{job_id}/clip_b.mp4"}]}))
    (out / "clip_a.mp4").write_bytes(b"a" * 1000)
    (out / "clip_b.mp4").write_bytes(b"b" * 2000)
    return out


def test_same_second_downloads_get_separate_zips(tmp_path, monkeypatch):
    job_id = "job-zip"
    out = _make_job(tmp_path, job_id)
    monkeypatch.setattr(app, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(app, "_ensure_job_files", _no_files)
    monkeypatch.setattr(app.time, "time", lambda: 1_700_000_000.0)

    async def both():
        return await asyncio.gather(app.download_all_clips(job_id, None),
                                    app.download_all_clips(job_id, None))

    first, second = asyncio.run(both())
    assert first.path != second.path
    for resp in (first, second):
        with zipfile.ZipFile(resp.path) as zf:
            assert sorted(zf.namelist()) == ["clip_01_clip_a.mp4", "clip_02_clip_b.mp4"]
            assert zf.testzip() is None

    # Each cleanup removes only its own file, and a repeat is harmless.
    asyncio.run(first.background())
    assert not os.path.exists(first.path)
    assert os.path.exists(second.path)
    asyncio.run(first.background())
    asyncio.run(second.background())
    assert not list(out.glob("clips_*.zip"))
