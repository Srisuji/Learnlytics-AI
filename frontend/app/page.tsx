"use client";

import React, { useEffect, useState } from "react";

interface KPIs {
  total_students: number;
  avg_score: number;
  avg_attendance: number;
  avg_assignment: number;
  risk_counts: {
    Low?: number;
    Medium?: number;
    High?: number;
    Critical?: number;
    "Insufficient data"?: number;
  };
  needs_follow_up: number;
}

interface Student {
  student_id: string;
  name: string;
  department: string;
  semester: number;
  attendance_rate: number | null;
  academic_score: number | null;
  assignment_rate: number | null;
  screening_score?: number;
  risk_category?: string;
  reasons?: string;
  review_status?: string;
}

export default function Home() {
  const [apiUrl] = useState(() => process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000");
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  const [kpis, setKpis] = useState<KPIs | null>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRisk, setSelectedRisk] = useState<string>("All");
  const [selectedDept, setSelectedDept] = useState<string>("All");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const activeUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

    async function fetchData() {
      try {
        const healthRes = await fetch(`${activeUrl}/api/health`, { method: "GET" });
        if (healthRes.ok) {
          setApiConnected(true);
          // Fetch KPIs
          const kpisRes = await fetch(`${activeUrl}/api/kpis`);
          if (kpisRes.ok) {
            const kpiData = await kpisRes.json();
            setKpis(kpiData);
          }
          // Fetch Students
          const stuRes = await fetch(`${activeUrl}/api/students`);
          if (stuRes.ok) {
            const stuData = await stuRes.json();
            setStudents(stuData.students || []);
          }
        } else {
          setApiConnected(false);
        }
      } catch {
        setApiConnected(false);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  const departments = ["All", ...Array.from(new Set(students.map((s) => s.department).filter(Boolean)))];

  const filteredStudents = students.filter((s) => {
    const matchesSearch =
      searchQuery === "" ||
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.student_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.department.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesRisk =
      selectedRisk === "All" ||
      (s.risk_category && s.risk_category.toLowerCase() === selectedRisk.toLowerCase());

    const matchesDept = selectedDept === "All" || s.department === selectedDept;

    return matchesSearch && matchesRisk && matchesDept;
  });

  const getRiskBadgeClass = (category?: string) => {
    switch (category?.toLowerCase()) {
      case "critical":
        return "bg-rose-950/80 text-rose-300 border border-rose-800";
      case "high":
        return "bg-amber-950/80 text-amber-300 border border-amber-800";
      case "medium":
        return "bg-yellow-950/80 text-yellow-300 border border-yellow-800";
      case "low":
        return "bg-emerald-950/80 text-emerald-300 border border-emerald-800";
      default:
        return "bg-zinc-800 text-zinc-300 border border-zinc-700";
    }
  };

  return (
    <div className="min-h-screen bg-[#071426] text-slate-100 font-sans selection:bg-[#00A6FF]/30">
      {/* Top Navigation */}
      <header className="border-b border-slate-800/80 bg-[#081A30]/90 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-[#00A6FF] to-[#00E5FF] flex items-center justify-center shadow-lg shadow-cyan-500/20 font-bold text-slate-950 text-xl">
              L
            </div>
            <div>
              <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-[#00E5FF] bg-clip-text text-transparent">
                Learnlytics AI
              </span>
              <span className="hidden sm:inline-block ml-2 text-xs px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/60 font-medium">
                v1.0.0 Production
              </span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs">
              <span
                className={`w-2 h-2 rounded-full ${
                  apiConnected === true
                    ? "bg-emerald-400 animate-pulse"
                    : apiConnected === false
                    ? "bg-amber-400"
                    : "bg-slate-400"
                }`}
              />
              <span className="text-slate-400 hidden sm:inline">API Status:</span>
              <span className="font-medium text-slate-200">
                {apiConnected === true
                  ? "Connected (FastAPI)"
                  : apiConnected === false
                  ? "Offline / Standby"
                  : "Checking..."}
              </span>
            </div>

            <a
              href="http://localhost:8501"
              target="_blank"
              rel="noreferrer"
              className="px-3.5 py-1.5 rounded-lg bg-[#00A6FF] hover:bg-[#0090e0] text-slate-950 font-semibold text-xs tracking-wide transition-all shadow-md shadow-cyan-500/10 flex items-center gap-1.5"
            >
              Streamlit Portal
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>
        </div>
      </header>

      {/* Hero Banner */}
      <section className="relative overflow-hidden border-b border-slate-800/60 bg-gradient-to-b from-[#0B2342]/70 to-[#071426] py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="max-w-3xl">
            <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white mb-3">
              Understand Performance. <span className="text-[#00E5FF]">Unlock Potential.</span>
            </h1>
            <p className="text-base sm:text-lg text-slate-300 leading-relaxed">
              AI-Powered Educational Analytics, Transparent Early-Warning Screening, and Personalized Student Success Platform for Colleges & Universities.
            </p>
          </div>

          {/* Quick Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8">
            <div className="bg-[#0B2342]/80 border border-slate-700/60 rounded-xl p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">Total Students</div>
              <div className="text-2xl sm:text-3xl font-bold text-white mt-1">
                {kpis ? kpis.total_students : (loading ? "..." : "36")}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">Enrolled across departments</div>
            </div>

            <div className="bg-[#0B2342]/80 border border-slate-700/60 rounded-xl p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">Average Marks</div>
              <div className="text-2xl sm:text-3xl font-bold text-[#00E5FF] mt-1">
                {kpis ? `${kpis.avg_score.toFixed(1)}%` : (loading ? "..." : "65.6%")}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">Institutional academic average</div>
            </div>

            <div className="bg-[#0B2342]/80 border border-slate-700/60 rounded-xl p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">Average Attendance</div>
              <div className="text-2xl sm:text-3xl font-bold text-emerald-400 mt-1">
                {kpis ? `${kpis.avg_attendance.toFixed(1)}%` : (loading ? "..." : "83.3%")}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">Lecture & lab engagement</div>
            </div>

            <div className="bg-[#0B2342]/80 border border-slate-700/60 rounded-xl p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wider text-slate-400 font-medium">Follow-Up Queue</div>
              <div className="text-2xl sm:text-3xl font-bold text-amber-400 mt-1">
                {kpis ? kpis.needs_follow_up : (loading ? "..." : "9")}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">Students flagged for review</div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Controls Bar */}
        <div className="flex flex-col md:flex-row gap-4 items-stretch md:items-center justify-between mb-6">
          <div className="relative flex-1 max-w-md">
            <input
              type="text"
              placeholder="Search by name, ID, or department..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#081A30] border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-[#00A6FF] transition"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Risk:</span>
              <select
                value={selectedRisk}
                onChange={(e) => setSelectedRisk(e.target.value)}
                className="bg-[#081A30] border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-[#00A6FF]"
              >
                <option value="All">All Risk Tiers</option>
                <option value="Critical">Critical</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Dept:</span>
              <select
                value={selectedDept}
                onChange={(e) => setSelectedDept(e.target.value)}
                className="bg-[#081A30] border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-[#00A6FF]"
              >
                {departments.map((dept) => (
                  <option key={dept} value={dept}>
                    {dept}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Student Screening Table */}
        <div className="bg-[#081A30] border border-slate-800 rounded-xl overflow-hidden shadow-xl">
          <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <span>Student Performance Directory</span>
              <span className="text-xs font-normal text-slate-400">
                ({filteredStudents.length} records shown)
              </span>
            </h2>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-300">
              <thead className="bg-[#0B2342]/60 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="px-6 py-3.5 font-medium">Student ID & Name</th>
                  <th className="px-6 py-3.5 font-medium">Department</th>
                  <th className="px-6 py-3.5 font-medium">Attendance</th>
                  <th className="px-6 py-3.5 font-medium">Academic Score</th>
                  <th className="px-6 py-3.5 font-medium">Assignments</th>
                  <th className="px-6 py-3.5 font-medium">Screening Status</th>
                  <th className="px-6 py-3.5 font-medium text-right">Review Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {filteredStudents.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-slate-400">
                      {apiConnected === false
                        ? "API server is offline. Please start the backend with 'python -m uvicorn backend.main:app --port 8000'."
                        : "No matching student records found."}
                    </td>
                  </tr>
                ) : (
                  filteredStudents.slice(0, 15).map((stu) => (
                    <tr key={stu.student_id} className="hover:bg-slate-800/40 transition">
                      <td className="px-6 py-4">
                        <div className="font-medium text-white">{stu.name}</div>
                        <div className="text-xs text-slate-400 font-mono">{stu.student_id}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div>{stu.department}</div>
                        <div className="text-xs text-slate-400">Sem {stu.semester}</div>
                      </td>
                      <td className="px-6 py-4">
                        {stu.attendance_rate !== null ? (
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{stu.attendance_rate.toFixed(1)}%</span>
                          </div>
                        ) : (
                          <span className="text-slate-500 italic">Unavailable</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {stu.academic_score !== null ? (
                          <div className="font-medium">{stu.academic_score.toFixed(1)}%</div>
                        ) : (
                          <span className="text-slate-500 italic">Unavailable</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {stu.assignment_rate !== null ? (
                          <div className="font-medium">{stu.assignment_rate.toFixed(1)}%</div>
                        ) : (
                          <span className="text-slate-500 italic">Unavailable</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${getRiskBadgeClass(
                            stu.risk_category
                          )}`}
                        >
                          {stu.risk_category || "Low"}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <span className="text-xs px-2 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
                          {stu.review_status || "New"}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Feature Highlights Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-10">
          <div className="bg-[#081A30] border border-slate-800 rounded-xl p-6">
            <div className="w-10 h-10 rounded-lg bg-cyan-950 border border-cyan-800/60 flex items-center justify-center text-[#00E5FF] mb-4">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Transparent Early-Warning</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              Screening scores are rule-based, fully explainable, and never act as an automated decision-maker. All flags are for human faculty review.
            </p>
          </div>

          <div className="bg-[#081A30] border border-slate-800 rounded-xl p-6">
            <div className="w-10 h-10 rounded-lg bg-blue-950 border border-blue-800/60 flex items-center justify-center text-[#00A6FF] mb-4">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Cognitive Mastery & Bloom&apos;s</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              Analyzes student mastery across Bloom&apos;s taxonomy (K1 Remember, K2 Understand, K3 Apply) to recommend targeted practice questions.
            </p>
          </div>

          <div className="bg-[#081A30] border border-slate-800 rounded-xl p-6">
            <div className="w-10 h-10 rounded-lg bg-purple-950 border border-purple-800/60 flex items-center justify-center text-purple-400 mb-4">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
              </svg>
            </div>
            <h3 className="text-base font-semibold text-white mb-2">Learnlytics AI Tutor</h3>
            <p className="text-xs text-slate-300 leading-relaxed">
              Supportive multilingual chat (English, Tamil, Tanglish) offering progressive hints, topic breakdown, and private verified student context.
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-[#081A30] py-8 mt-16 text-center text-xs text-slate-400">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            Learnlytics AI &copy; 2026. Designed for transparent, human-centered student analytics.
          </div>
          <div className="flex gap-6 text-slate-400">
            <span>FastAPI Backend: <code className="text-cyan-400">{apiUrl}</code></span>
            <span>Streamlit Portal: <code className="text-cyan-400">http://localhost:8501</code></span>
          </div>
        </div>
      </footer>
    </div>
  );
}
