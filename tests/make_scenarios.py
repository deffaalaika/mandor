#!/usr/bin/env python3
"""Build throwaway scenarios for pressure-testing the mandor skill (not part of the unit suite).

Usage: python3 tests/make_scenarios.py <out-dir>
Creates:
  <out>/repo-plan     fixture repo, clean, for a /mandor planning scenario
  <out>/repo-verify   same fixture + 2 commits from the "local model" (step 2 deviates)
  <out>/plans/valas   plan folder (outside both repos) matching repo-verify
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import (execute_step, full_block, git, real_rules, search_block,  # noqa: E402
                     step_text, write_files, commit_all)

PKG = "app/src/main/java/com/example/valas"
TEST_PKG = "app/src/test/java/com/example/valas"

FILES = {
    "settings.gradle.kts": 'rootProject.name = "valas-sample"\ninclude(":app")\n',
    "app/build.gradle.kts": (
        "plugins { id(\"com.android.application\"); kotlin(\"android\") }\n\n"
        "dependencies {\n"
        "    implementation(\"org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0\")\n"
        "    testImplementation(\"junit:junit:4.13.2\")\n"
        "    testImplementation(\"org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0\")\n"
        "}\n"
    ),
    PKG + "/RateDto.kt": "package com.example.valas\n\ndata class RateDto(val code: String, val rate: Double?)\n",
    PKG + "/ValasApi.kt": (
        "package com.example.valas\n\n"
        "interface ValasApi {\n"
        "    /** Returns null when the currency is not supported by the backend. */\n"
        "    suspend fun getRate(code: String): RateDto?\n"
        "}\n"
    ),
    PKG + "/ValasRepository.kt": (
        "package com.example.valas\n\n"
        "class ValasRepository(private val api: ValasApi) {\n\n"
        "    suspend fun rate(code: String): Double {\n"
        "        val dto = api.getRate(code)!!\n"
        "        return dto.rate!!\n"
        "    }\n"
        "}\n"
    ),
    PKG + "/ValasViewModel.kt": (
        "package com.example.valas\n\n"
        "import kotlinx.coroutines.flow.MutableStateFlow\n"
        "import kotlinx.coroutines.flow.StateFlow\n\n"
        "class ValasViewModel(private val repo: ValasRepository) {\n"
        "    private val _rate = MutableStateFlow<Double?>(null)\n"
        "    val rate: StateFlow<Double?> = _rate\n\n"
        "    suspend fun load(code: String) {\n"
        "        _rate.value = repo.rate(code)\n"
        "    }\n"
        "}\n"
    ),
    TEST_PKG + "/ValasRepositoryTest.kt": (
        "package com.example.valas\n\n"
        "import kotlinx.coroutines.test.runTest\n"
        "import org.junit.Assert.assertEquals\n"
        "import org.junit.Test\n\n"
        "class ValasRepositoryTest {\n"
        "    private class FakeApi(val dto: RateDto?) : ValasApi {\n"
        "        override suspend fun getRate(code: String) = dto\n"
        "    }\n\n"
        "    @Test\n"
        "    fun rateReturnsValue() = runTest {\n"
        "        val repo = ValasRepository(FakeApi(RateDto(\"USD\", 15500.0)))\n"
        "        assertEquals(15500.0, repo.rate(\"USD\"), 0.0)\n"
        "    }\n"
        "}\n"
    ),
}

REPO_FILE = PKG + "/ValasRepository.kt"
RESULT_FILE = PKG + "/RateResult.kt"


def make_repo_at(path: Path) -> str:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    write_files(path, FILES)
    return commit_all(path, "Initial valas feature")


def plan_steps():
    s1 = step_text(
        1, "Add RateResult type", ["- CREATE %s (FULL FILE)" % RESULT_FILE], ["- none"],
        full_block(RESULT_FILE, "package com.example.valas\n\nsealed class RateResult {\n"
                                "    data class Success(val rate: Double) : RateResult()\n"
                                "    object Unavailable : RateResult()\n}\n"),
        rules=real_rules())
    s2 = step_text(
        2, "Repository returns RateResult instead of crashing",
        ["- MODIFY %s (ANCHOR EDIT)" % REPO_FILE], ["- %s:1-6" % (PKG + "/ValasApi.kt")],
        search_block(REPO_FILE,
                     "    suspend fun rate(code: String): Double {\n"
                     "        val dto = api.getRate(code)!!\n"
                     "        return dto.rate!!\n"
                     "    }",
                     "    suspend fun rate(code: String): RateResult {\n"
                     "        val value = api.getRate(code)?.rate ?: return RateResult.Unavailable\n"
                     "        return RateResult.Success(value)\n"
                     "    }"),
        rules=real_rules())
    return s1, s2


def main(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    make_repo_at(out / "repo-plan")
    base = make_repo_at(out / "repo-verify")
    s1, s2 = plan_steps()
    plan = out / "plans" / "valas"
    plan.mkdir(parents=True)
    (plan / "step-1.md").write_text(s1, encoding="utf-8")
    (plan / "step-2.md").write_text(s2, encoding="utf-8")
    (plan / "meta").write_text(
        "repo=%s\nbase=%s\nsteps=2\nrevision=1\nstatus=ready\ncreated=2026-11-24\n"
        "task=fix crash valas saat rate null\n" % ((out / "repo-verify").resolve(), base),
        encoding="utf-8")
    (plan / "verify.md").write_text(
        "- Unit test: ./gradlew :app:testDebugUnitTest --tests '*ValasRepositoryTest'\n"
        "- Device: buka layar Valas, pilih mata uang tidak didukung (XYZ), app tidak crash, "
        "muncul teks 'Kurs tidak tersedia'.\n", encoding="utf-8")
    repo = out / "repo-verify"
    execute_step(repo, s1, msg="add RateResult")

    def deviate(r: Path):
        p = r / REPO_FILE
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace("?: return RateResult.Unavailable", "?: 0.0"), encoding="utf-8")
        tp = r / (TEST_PKG + "/ValasRepositoryTest.kt")
        tt = tp.read_text(encoding="utf-8")
        tp.write_text(tt.replace("    @Test\n", "    @Ignore\n    @Test\n"), encoding="utf-8")

    execute_step(repo, s2, mutate=deviate, msg="repo returns RateResult")
    print(out)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
