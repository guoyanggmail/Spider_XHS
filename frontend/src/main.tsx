import React, { FormEvent, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Summary = {
  primary_account_total: number;
  worker_cookie_total: number;
  worker_cookie_active: number;
  publish_pending: number;
  publish_success: number;
  search_task_total: number;
  search_result_total: number;
  analytics_task_total: number;
  analytics_snapshot_total: number;
  online_device_total: number;
  latest_logs: Array<{ id: string; log_type: string; message: string; created_at: string }>;
};

type Account = {
  id: string;
  account_type: string;
  name: string;
  nickname: string;
  cookie_preview: string;
  status: string;
  remark: string;
  bound_device_id: string;
  is_busy?: boolean;
  runtime_state?: string;
  last_check_at?: string | null;
  cooldown_until?: string | null;
  failure_count: number;
};

type PublishTask = {
  id: string;
  account_id: string;
  title: string;
  desc: string;
  topics: string[];
  location: string;
  media_type: string;
  media_urls: string[];
  cover_url: string;
  review_status: string;
  task_status: string;
  scheduled_at?: string | null;
  claim_expires_at?: string | null;
  last_error: string;
};

type PublishStatusMeta = {
  label: string;
  tone: string;
};

type SearchTask = {
  id: string;
  keyword: string;
  group_name: string;
  require_num: number;
  interval_minutes: number;
  task_status: string;
  enabled: boolean;
  last_run_at?: string | null;
  last_error: string;
};

type SearchResult = {
  id: string;
  search_task_id: string;
  post_id: string;
  post_url: string;
  title: string;
  content_preview: string;
  content: string;
  note_type: string;
  topics: string[];
  image_urls: string[];
  video_url: string;
  video_cover_url: string;
  author_avatar: string;
  cover_url: string;
  location: string;
  author_name: string;
  like_count: number;
  comment_count: number;
  collect_count: number;
  review_status: string;
  review_note: string;
  hidden: boolean;
  created_at: string;
};

type AnalyticsTask = {
  id: string;
  account_id: string;
  group_name: string;
  interval_minutes: number;
  task_status: string;
  enabled: boolean;
  last_run_at?: string | null;
  last_error: string;
};

type AnalyticsSnapshot = {
  id: string;
  account_id: string;
  nickname: string;
  follower_count: number;
  liked_total: number;
  post_total: number;
  collected_total?: number | null;
  posts: Array<{
    id: string;
    post_id: string;
    title: string;
    like_count: number;
    comment_count: number;
    collect_count: number;
  }>;
  created_at: string;
};

type Device = {
  id: string;
  device_id: string;
  app_instance_id: string;
  device_name: string;
  app_version: string;
  status: string;
  last_heartbeat_at?: string | null;
};

type AuditLog = {
  id: string;
  log_type: string;
  operator_type: string;
  operator_id: string;
  target_type: string;
  target_id: string;
  message: string;
  created_at: string;
};

type WorkerAuthMode = "cookie" | "sms" | "qrcode";

type WorkerSmsSession = {
  login_session_id: string;
  expires_in_seconds: number;
};

type WorkerQrSession = {
  login_session_id: string;
  expires_in_seconds: number;
  qr_url: string;
  qr_data_url: string;
};

type TabKey =
  | "dashboard"
  | "primary"
  | "workers"
  | "publish"
  | "search"
  | "results"
  | "analytics"
  | "devices"
  | "logs";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "dashboard", label: "概览" },
  { key: "primary", label: "主账号" },
  { key: "workers", label: "小号池" },
  { key: "publish", label: "发帖任务" },
  { key: "search", label: "关键词任务" },
  { key: "results", label: "采集结果" },
  { key: "analytics", label: "账号监控" },
  { key: "devices", label: "设备" },
  { key: "logs", label: "日志" }
];

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

function StatusBanner({ message }: { message: string }) {
  if (!message) return null;
  return <div className="rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm text-slate-700 shadow-sm">{message}</div>;
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold text-slate-900">{title}</h2>
      {children}
    </section>
  );
}

function formatTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "无";
}

function getPublishStatusMeta(taskStatus: string): PublishStatusMeta {
  if (taskStatus === "success") {
    return { label: "发布成功", tone: "bg-emerald-50 text-emerald-700 ring-emerald-100" };
  }
  if (taskStatus === "failed" || taskStatus === "cancelled") {
    return { label: "发布失败", tone: "bg-rose-50 text-rose-700 ring-rose-100" };
  }
  return { label: "待发布", tone: "bg-amber-50 text-amber-700 ring-amber-100" };
}

function toMediaProxyUrl(url?: string | null) {
  const candidate = (url || "").trim();
  if (!candidate) return "";
  return `/api/media-proxy?url=${encodeURIComponent(candidate)}`;
}

function App() {
  const [tab, setTab] = useState<TabKey>("dashboard");
  const [message, setMessage] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [primaryAccounts, setPrimaryAccounts] = useState<Account[]>([]);
  const [workerCookies, setWorkerCookies] = useState<Account[]>([]);
  const [publishTasks, setPublishTasks] = useState<PublishTask[]>([]);
  const [searchTasks, setSearchTasks] = useState<SearchTask[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [analyticsTasks, setAnalyticsTasks] = useState<AnalyticsTask[]>([]);
  const [analyticsSnapshots, setAnalyticsSnapshots] = useState<AnalyticsSnapshot[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [workerForm, setWorkerForm] = useState({
    name: "",
    cookies: "",
    remark: "",
    phone: "",
    code: ""
  });
  const [workerAuthMode, setWorkerAuthMode] = useState<WorkerAuthMode>("cookie");
  const [workerSmsSession, setWorkerSmsSession] = useState<WorkerSmsSession | null>(null);
  const [workerQrSession, setWorkerQrSession] = useState<WorkerQrSession | null>(null);
  const [publishForm, setPublishForm] = useState({
    account_id: "",
    title: "",
    desc: "",
    topics: "",
    location: "",
    media_type: "image",
    media_urls: "",
    cover_url: "",
    review_status: "approved"
  });
  const [searchForm, setSearchForm] = useState({
    keyword: "",
    require_num: 10,
    interval_minutes: 120
  });
  const [analyticsForm, setAnalyticsForm] = useState({
    account_id: "",
    interval_minutes: 360
  });

  async function loadAll() {
    const [
      summaryRes,
      accountsRes,
      publishRes,
      searchTaskRes,
      searchResultRes,
      analyticsTaskRes,
      analyticsSnapshotRes,
      devicesRes,
      logsRes
    ] = await Promise.all([
      api<{ summary: Summary }>("/api/ops/summary"),
      api<{ primary_accounts: Account[]; worker_cookies: Account[] }>("/api/accounts"),
      api<{ tasks: PublishTask[] }>("/api/publish-tasks"),
      api<{ tasks: SearchTask[] }>("/api/search-tasks"),
      api<{ results: SearchResult[] }>("/api/search-results"),
      api<{ tasks: AnalyticsTask[] }>("/api/analytics-tasks"),
      api<{ snapshots: AnalyticsSnapshot[] }>("/api/analytics-snapshots"),
      api<{ devices: Device[] }>("/api/devices"),
      api<{ logs: AuditLog[] }>("/api/logs")
    ]);

    setSummary(summaryRes.summary);
    setPrimaryAccounts(accountsRes.primary_accounts);
    setWorkerCookies(accountsRes.worker_cookies);
    setPublishTasks(publishRes.tasks);
    setSearchTasks(searchTaskRes.tasks);
    setSearchResults(searchResultRes.results);
    setAnalyticsTasks(analyticsTaskRes.tasks);
    setAnalyticsSnapshots(analyticsSnapshotRes.snapshots);
    setDevices(devicesRes.devices);
    setLogs(logsRes.logs);
  }

  useEffect(() => {
    loadAll().catch((error: Error) => setMessage(error.message));
  }, []);

  async function submitWorker(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/api/cookie-workers", {
        method: "POST",
        body: JSON.stringify({
          ...workerForm
        })
      });
      setWorkerForm({ name: "", cookies: "", remark: "", phone: "", code: "" });
      setWorkerSmsSession(null);
      setWorkerQrSession(null);
      setMessage("小号 Cookie 已创建");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  function workerDraftPayload() {
    return {
      name: workerForm.name,
      remark: workerForm.remark,
      group_name: "",
      usage_tags: []
    };
  }

  async function requestWorkerSmsCode() {
    try {
      const response = await api<WorkerSmsSession & { message: string }>("/api/cookie-workers/auth/request-sms-code", {
        method: "POST",
        body: JSON.stringify({
          ...workerDraftPayload(),
          phone: workerForm.phone,
          zone: "86"
        })
      });
      setWorkerSmsSession({
        login_session_id: response.login_session_id,
        expires_in_seconds: response.expires_in_seconds
      });
      setMessage(response.message || "验证码已发送");
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function loginWorkerWithSms() {
    try {
      if (!workerSmsSession) throw new Error("请先获取验证码");
      const response = await api<{ message: string; worker_cookie: Account }>("/api/cookie-workers/auth/login-with-sms", {
        method: "POST",
        body: JSON.stringify({
          ...workerDraftPayload(),
          login_session_id: workerSmsSession.login_session_id,
          phone: workerForm.phone,
          code: workerForm.code,
          zone: "86"
        })
      });
      setWorkerForm({ name: "", cookies: "", remark: "", phone: "", code: "" });
      setWorkerSmsSession(null);
      setWorkerQrSession(null);
      setMessage(response.message || "小号已创建");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function requestWorkerQrCode() {
    try {
      const response = await api<WorkerQrSession & { message: string }>("/api/cookie-workers/auth/request-qrcode", {
        method: "POST",
        body: JSON.stringify(workerDraftPayload())
      });
      setWorkerQrSession({
        login_session_id: response.login_session_id,
        expires_in_seconds: response.expires_in_seconds,
        qr_url: response.qr_url,
        qr_data_url: response.qr_data_url
      });
      setMessage(response.message || "二维码已生成");
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function checkWorkerQrCode() {
    try {
      if (!workerQrSession) throw new Error("请先生成二维码");
      const response = await api<{ success: boolean; message: string; worker_cookie?: Account }>("/api/cookie-workers/auth/check-qrcode", {
        method: "POST",
        body: JSON.stringify({
          ...workerDraftPayload(),
          login_session_id: workerQrSession.login_session_id
        })
      });
      setMessage(response.message);
      if (response.success) {
        setWorkerForm({ name: "", cookies: "", remark: "", phone: "", code: "" });
        setWorkerQrSession(null);
        setWorkerSmsSession(null);
        await loadAll();
      }
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function submitPublishTask(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/api/publish-tasks", {
        method: "POST",
        body: JSON.stringify({
          ...publishForm,
          topics: publishForm.topics.split(",").map((item) => item.trim()).filter(Boolean),
          media_urls: publishForm.media_urls.split("\n").map((item) => item.trim()).filter(Boolean)
        })
      });
      setMessage("发帖任务已创建");
      setPublishForm({
        account_id: primaryAccounts[0]?.id || "",
        title: "",
        desc: "",
        topics: "",
        location: "",
        media_type: "image",
        media_urls: "",
        cover_url: "",
        review_status: "approved"
      });
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function submitSearchTask(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/api/search-tasks", { method: "POST", body: JSON.stringify(searchForm) });
      setSearchForm({ keyword: "", require_num: 10, interval_minutes: 120 });
      setMessage("关键词任务已创建");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function submitAnalyticsTask(event: FormEvent) {
    event.preventDefault();
    try {
      await api("/api/analytics-tasks", { method: "POST", body: JSON.stringify(analyticsForm) });
      setAnalyticsForm({ account_id: primaryAccounts[0]?.id || "", interval_minutes: 360 });
      setMessage("账号监控任务已创建");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function requeueTask(taskType: "publish" | "search" | "analytics", taskId: string) {
    const pathMap = {
      publish: "publish-tasks",
      search: "search-tasks",
      analytics: "analytics-tasks"
    };
    try {
      await api(`/api/${pathMap[taskType]}/${taskId}/requeue`, { method: "POST" });
      setMessage("任务已重新入队");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function toggleSearchTask(task: SearchTask) {
    try {
      await api(`/api/search-tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !task.enabled })
      });
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function updateSearchResult(item: SearchResult, patch: Partial<Pick<SearchResult, "review_status" | "hidden">>) {
    try {
      await api(`/api/search-results/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify(patch)
      });
      setMessage("采集结果已更新");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function toggleAnalyticsTask(task: AnalyticsTask) {
    try {
      await api(`/api/analytics-tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !task.enabled })
      });
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function deleteTask(taskType: "search" | "analytics", taskId: string) {
    try {
      await api(taskType === "search" ? `/api/search-tasks/${taskId}` : `/api/analytics-tasks/${taskId}`, { method: "DELETE" });
      setMessage(taskType === "search" ? "关键词任务已删除" : "账号监控任务已删除");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function runSearchTaskNow(task: SearchTask) {
    try {
      await api(`/api/search-tasks/${task.id}/run`, { method: "POST" });
      setMessage(`关键词任务“${task.keyword}”已立即执行`);
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function runAnalyticsTaskNow(task: AnalyticsTask) {
    try {
      await api(`/api/analytics-tasks/${task.id}/run`, { method: "POST" });
      setMessage(`账号监控任务已立即执行`);
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function checkPrimary(id: string) {
    try {
      const response = await api<{ success: boolean; message: string }>(`/api/accounts/primary/${id}/check`, { method: "POST" });
      setMessage(response.message || "主账号已校验");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function checkWorker(id: string) {
    try {
      const response = await api<{ success: boolean; message: string }>(`/api/cookie-workers/${id}/check`, { method: "POST" });
      setMessage(response.message || "小号 Cookie 已校验");
      await loadAll();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  useEffect(() => {
    if (!publishForm.account_id && primaryAccounts[0]?.id) {
      setPublishForm((current) => ({ ...current, account_id: primaryAccounts[0].id }));
    }
    if (!analyticsForm.account_id && primaryAccounts[0]?.id) {
      setAnalyticsForm((current) => ({ ...current, account_id: primaryAccounts[0].id }));
    }
  }, [primaryAccounts, publishForm.account_id, analyticsForm.account_id]);

  function getAccountName(accountId: string) {
    return primaryAccounts.find((account) => account.id === accountId)?.name || "未匹配账号";
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <header className="mb-8 rounded-3xl bg-slate-900 px-6 py-8 text-white shadow-xl">
          <p className="text-sm uppercase tracking-[0.3em] text-slate-300">Spider XHS</p>
          <h1 className="mt-2 text-3xl font-semibold">App 执行端管理后台</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-300">
            主账号只负责发帖，小号池负责搜索和监控采集。当前页面只做任务、账号、设备和审计管理。
          </p>
        </header>

        <StatusBanner message={message} />

        <nav className="my-6 flex flex-wrap gap-2">
          {tabs.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                tab === item.key ? "bg-slate-900 text-white" : "bg-white text-slate-700 shadow-sm"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {tab === "dashboard" && summary && (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {[
              ["主账号", summary.primary_account_total],
              ["小号池", summary.worker_cookie_total],
              ["可用小号", summary.worker_cookie_active],
              ["待发任务", summary.publish_pending],
              ["已发成功", summary.publish_success],
              ["关键词任务", summary.search_task_total],
              ["采集结果", summary.search_result_total],
              ["监控任务", summary.analytics_task_total],
              ["监控快照", summary.analytics_snapshot_total],
              ["在线设备", summary.online_device_total]
            ].map(([label, value]) => (
              <Card key={label} title={String(label)}>
                <div className="text-3xl font-semibold">{value}</div>
              </Card>
            ))}
            <div className="md:col-span-2 xl:col-span-5">
              <Card title="最近日志">
                <div className="space-y-3">
                  {summary.latest_logs.map((log) => (
                    <div key={log.id} className="rounded-xl bg-slate-50 px-4 py-3 text-sm">
                      <div className="font-medium">{log.message}</div>
                      <div className="mt-1 text-xs text-slate-500">
                        {log.log_type} · {new Date(log.created_at).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        )}

        {tab === "primary" && (
          <div className="space-y-6">
            <Card title="主账号说明">
              <div className="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                Web 端只负责查看主账号状态和校验结果。主账号新增、登录和 Cookie 更新只在 Android 端处理。
              </div>
            </Card>
            <Card title="主账号列表">
              <div className="space-y-4">
                {primaryAccounts.map((account) => (
                  <div key={account.id} className="rounded-2xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold">{account.name}</div>
                        <div className="text-sm text-slate-500">{account.nickname || "无昵称"} · {account.cookie_preview}</div>
                        <div className="mt-1 text-xs text-slate-500">状态 {account.status} · 绑定设备 {account.bound_device_id || "未绑定"} · 最近校验 {formatTime(account.last_check_at)}</div>
                        {account.remark ? <div className="mt-2 text-xs text-slate-500">备注 {account.remark}</div> : null}
                      </div>
                      <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => checkPrimary(account.id)}>校验</button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {tab === "workers" && (
          <div className="grid gap-6 lg:grid-cols-[360px,1fr]">
            <Card title="新增小号 Cookie">
              <form className="space-y-3" onSubmit={submitWorker}>
                <div className="flex flex-wrap gap-2">
                  {[
                    ["cookie", "直接 Cookie"],
                    ["sms", "验证码"],
                    ["qrcode", "扫码"]
                  ].map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setWorkerAuthMode(value as WorkerAuthMode)}
                      className={`rounded-full px-3 py-1 text-sm ${
                        workerAuthMode === value ? "bg-slate-900 text-white" : "border border-slate-300 bg-white text-slate-700"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <input className="w-full rounded-xl border px-3 py-2" placeholder="账号名称" value={workerForm.name} onChange={(e) => setWorkerForm({ ...workerForm, name: e.target.value })} />
                {workerAuthMode === "cookie" && (
                  <textarea className="h-32 w-full rounded-xl border px-3 py-2" placeholder="Worker Cookie" value={workerForm.cookies} onChange={(e) => setWorkerForm({ ...workerForm, cookies: e.target.value })} />
                )}
                {workerAuthMode === "sms" && (
                  <>
                    <input className="w-full rounded-xl border px-3 py-2" placeholder="手机号" value={workerForm.phone} onChange={(e) => setWorkerForm({ ...workerForm, phone: e.target.value.replace(/\D/g, "").slice(0, 11) })} />
                    <input className="w-full rounded-xl border px-3 py-2" placeholder="验证码" value={workerForm.code} onChange={(e) => setWorkerForm({ ...workerForm, code: e.target.value.replace(/\D/g, "").slice(0, 6) })} />
                    {workerSmsSession ? <div className="text-xs text-slate-500">验证码会话已创建，{workerSmsSession.expires_in_seconds} 秒内有效</div> : null}
                    <div className="flex flex-wrap gap-2">
                      <button className="rounded-xl border px-4 py-2" type="button" onClick={requestWorkerSmsCode}>获取验证码</button>
                      <button className="rounded-xl bg-slate-900 px-4 py-2 text-white" type="button" onClick={loginWorkerWithSms}>验证码登录并保存</button>
                    </div>
                  </>
                )}
                {workerAuthMode === "qrcode" && (
                  <>
                    <div className="flex flex-wrap gap-2">
                      <button className="rounded-xl border px-4 py-2" type="button" onClick={requestWorkerQrCode}>生成二维码</button>
                      <button className="rounded-xl bg-slate-900 px-4 py-2 text-white" type="button" onClick={checkWorkerQrCode}>检查扫码状态</button>
                    </div>
                    {workerQrSession ? (
                      <div className="space-y-2 rounded-xl border border-slate-200 p-3">
                        <img src={workerQrSession.qr_data_url} alt="扫码登录二维码" className="h-48 w-48 rounded-lg border border-slate-200 bg-white p-2" />
                        <div className="text-xs text-slate-500">二维码有效期 {workerQrSession.expires_in_seconds} 秒</div>
                        <a className="break-all text-xs text-sky-700 underline" href={workerQrSession.qr_url} target="_blank" rel="noreferrer">
                          {workerQrSession.qr_url}
                        </a>
                      </div>
                    ) : null}
                  </>
                )}
                <textarea className="h-20 w-full rounded-xl border px-3 py-2" placeholder="备注" value={workerForm.remark} onChange={(e) => setWorkerForm({ ...workerForm, remark: e.target.value })} />
                {workerAuthMode === "cookie" ? (
                  <button className="rounded-xl bg-slate-900 px-4 py-2 text-white" type="submit">保存小号</button>
                ) : null}
              </form>
            </Card>
            <Card title="小号池列表">
              <div className="space-y-4">
                {workerCookies.map((account) => (
                  <div key={account.id} className="rounded-2xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold">{account.name}</div>
                        <div className="text-sm text-slate-500">{account.cookie_preview}</div>
                        <div className="mt-1 text-xs text-slate-500">
                          状态 {account.status} · {account.runtime_state === "busy" ? "忙碌中" : "空闲"}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">失败次数 {account.failure_count} · 最近校验 {formatTime(account.last_check_at)} · 冷却到 {formatTime(account.cooldown_until)}</div>
                        {account.remark ? <div className="mt-2 text-xs text-slate-500">备注 {account.remark}</div> : null}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button className="rounded-lg border px-3 py-1 text-sm" type="button" onClick={() => checkWorker(account.id)}>校验</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {tab === "publish" && (
          <div className="grid gap-6 lg:grid-cols-[380px,1fr]">
            <Card title="创建发帖任务">
              <form className="space-y-3" onSubmit={submitPublishTask}>
                <select className="w-full rounded-xl border px-3 py-2" value={publishForm.account_id} onChange={(e) => setPublishForm({ ...publishForm, account_id: e.target.value })}>
                  {primaryAccounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
                <input className="w-full rounded-xl border px-3 py-2" placeholder="标题" value={publishForm.title} onChange={(e) => setPublishForm({ ...publishForm, title: e.target.value })} />
                <textarea className="h-28 w-full rounded-xl border px-3 py-2" placeholder="正文" value={publishForm.desc} onChange={(e) => setPublishForm({ ...publishForm, desc: e.target.value })} />
                <input className="w-full rounded-xl border px-3 py-2" placeholder="话题，逗号分隔" value={publishForm.topics} onChange={(e) => setPublishForm({ ...publishForm, topics: e.target.value })} />
                <input className="w-full rounded-xl border px-3 py-2" placeholder="地点" value={publishForm.location} onChange={(e) => setPublishForm({ ...publishForm, location: e.target.value })} />
                <select className="w-full rounded-xl border px-3 py-2" value={publishForm.media_type} onChange={(e) => setPublishForm({ ...publishForm, media_type: e.target.value })}>
                  <option value="image">image</option>
                  <option value="video">video</option>
                </select>
                <textarea className="h-28 w-full rounded-xl border px-3 py-2" placeholder="媒体 URL，每行一个" value={publishForm.media_urls} onChange={(e) => setPublishForm({ ...publishForm, media_urls: e.target.value })} />
                <input className="w-full rounded-xl border px-3 py-2" placeholder="封面 URL（视频可选）" value={publishForm.cover_url} onChange={(e) => setPublishForm({ ...publishForm, cover_url: e.target.value })} />
                <button className="rounded-xl bg-slate-900 px-4 py-2 text-white" type="submit">创建任务</button>
              </form>
            </Card>
            <Card title="发帖任务列表">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {publishTasks.map((task) => (
                  <article key={task.id} className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
                    <div className="relative aspect-[3/4] overflow-hidden bg-slate-100">
                      {toMediaProxyUrl(task.cover_url || task.media_urls[0]) ? (
                        <img
                          src={toMediaProxyUrl(task.cover_url || task.media_urls[0])}
                          alt={task.title}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full items-center justify-center bg-[linear-gradient(180deg,#f8fafc_0%,#e2e8f0_100%)] text-sm font-medium text-slate-400">
                          暂无封面
                        </div>
                      )}
                      <div className="absolute inset-x-0 top-0 flex items-center justify-between p-3">
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${getPublishStatusMeta(task.task_status).tone}`}>
                          {getPublishStatusMeta(task.task_status).label}
                        </span>
                        <span className="rounded-full bg-black/55 px-3 py-1 text-xs font-medium text-white">
                          {task.media_type === "video" ? "视频" : `${task.media_urls.length || 0} 图`}
                        </span>
                      </div>
                    </div>
                    <div className="space-y-3 p-4">
                      <div className="space-y-2">
                        <div className="line-clamp-2 text-base font-semibold leading-6 text-slate-900">{task.title}</div>
                        {task.desc ? <div className="line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-600">{task.desc}</div> : null}
                        {task.topics.length ? (
                          <div className="flex flex-wrap gap-2">
                            {task.topics.map((topic) => (
                              <span key={topic} className="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-600">
                                #{topic}
                              </span>
                            ))}
                          </div>
                        ) : null}
                      </div>
                      <div className="space-y-1 text-xs text-slate-500">
                        <div>主账号 {getAccountName(task.account_id)}</div>
                        <div>位置 {task.location || "未填写"} · 计划时间 {formatTime(task.scheduled_at)}</div>
                        <div>执行状态 {task.claim_expires_at ? `执行中，领取到 ${formatTime(task.claim_expires_at)}` : "未领取"}</div>
                      </div>
                      {task.last_error ? <div className="rounded-2xl bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">{task.last_error}</div> : null}
                      <div className="flex flex-wrap gap-2">
                        {task.task_status === "failed" ? (
                          <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => requeueTask("publish", task.id)}>重新发布</button>
                        ) : null}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </Card>
          </div>
        )}

        {tab === "search" && (
          <div className="grid gap-6 lg:grid-cols-[360px,1fr]">
            <Card title="创建关键词任务">
              <form className="space-y-3" onSubmit={submitSearchTask}>
                <input className="w-full rounded-xl border px-3 py-2" placeholder="关键词" value={searchForm.keyword} onChange={(e) => setSearchForm({ ...searchForm, keyword: e.target.value })} />
                <input className="w-full rounded-xl border px-3 py-2" type="number" placeholder="单次数量" value={searchForm.require_num} onChange={(e) => setSearchForm({ ...searchForm, require_num: Number(e.target.value) })} />
                <input className="w-full rounded-xl border px-3 py-2" type="number" placeholder="间隔分钟" value={searchForm.interval_minutes} onChange={(e) => setSearchForm({ ...searchForm, interval_minutes: Number(e.target.value) })} />
                <button className="rounded-xl bg-slate-900 px-4 py-2 text-white" type="submit">创建任务</button>
              </form>
            </Card>
            <Card title="关键词任务列表">
              <div className="space-y-4">
                {searchTasks.map((task) => (
                  <div key={task.id} className="rounded-2xl border border-slate-200 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold">{task.keyword}</div>
                        <div className="text-sm text-slate-500">数量 {task.require_num} · 间隔 {task.interval_minutes} 分钟</div>
                        <div className="mt-1 text-xs text-slate-500">状态 {task.task_status} · {task.enabled ? "启用" : "停用"}</div>
                        <div className="mt-1 text-xs text-slate-500">最近执行 {task.last_run_at ? new Date(task.last_run_at).toLocaleString() : "无"}</div>
                        {task.last_error ? <div className="mt-2 text-xs text-rose-600">{task.last_error}</div> : null}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => toggleSearchTask(task)}>
                          {task.enabled ? "停用" : "启用"}
                        </button>
                        <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => runSearchTaskNow(task)}>立即执行</button>
                        <button className="rounded-lg border px-3 py-1 text-sm text-rose-600" onClick={() => deleteTask("search", task.id)}>删除任务</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}

        {tab === "results" && (
          <Card title="采集结果">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {searchResults.map((item) => (
                <article key={item.id} className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
                  <div className="relative aspect-[3/4] overflow-hidden bg-slate-100">
                    {toMediaProxyUrl(item.cover_url || item.video_cover_url || item.image_urls[0]) ? (
                      <img
                        src={toMediaProxyUrl(item.cover_url || item.video_cover_url || item.image_urls[0])}
                        alt={item.title || item.post_id}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center bg-[linear-gradient(180deg,#f8fafc_0%,#e2e8f0_100%)] text-sm font-medium text-slate-400">
                        暂无封面
                      </div>
                    )}
                    <div className="absolute inset-x-0 top-0 flex items-center justify-between p-3">
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${
                        item.hidden ? "bg-slate-100 text-slate-600 ring-slate-200" :
                        item.review_status === "valid" ? "bg-emerald-50 text-emerald-700 ring-emerald-100" :
                        item.review_status === "rejected" ? "bg-rose-50 text-rose-700 ring-rose-100" :
                        "bg-amber-50 text-amber-700 ring-amber-100"
                      }`}>
                        {item.hidden ? "已隐藏" : item.review_status === "valid" ? "有效" : item.review_status === "rejected" ? "无效" : "待处理"}
                      </span>
                      <span className="rounded-full bg-black/55 px-3 py-1 text-xs font-medium text-white">
                        {item.video_url ? "视频" : `${item.image_urls.length || 0} 图`}
                      </span>
                    </div>
                  </div>
                  <div className="space-y-3 p-4">
                    <div className="space-y-2">
                      <div className="line-clamp-2 text-base font-semibold leading-6 text-slate-900">{item.title || item.post_id}</div>
                      {(item.content || item.content_preview) ? <div className="line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-slate-600">{item.content || item.content_preview}</div> : null}
                      {item.topics.length ? (
                        <div className="flex flex-wrap gap-2">
                          {item.topics.map((topic) => (
                            <span key={topic} className="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-600">
                              #{topic}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    <div className="space-y-1 text-xs text-slate-500">
                      <div>{item.author_name || "未知作者"} · 点赞 {item.like_count} · 评论 {item.comment_count} · 收藏 {item.collect_count}</div>
                      <div>位置 {item.location || "未填写"} · 采集时间 {formatTime(item.created_at)}</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => updateSearchResult(item, { review_status: "valid" })}>有效</button>
                      <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => updateSearchResult(item, { review_status: "rejected" })}>无效</button>
                      <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => updateSearchResult(item, { hidden: !item.hidden })}>
                        {item.hidden ? "显示" : "隐藏"}
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </Card>
        )}

        {tab === "analytics" && (
          <div className="grid gap-6 lg:grid-cols-[360px,1fr]">
            <Card title="创建账号监控任务">
              <form className="space-y-3" onSubmit={submitAnalyticsTask}>
                <select className="w-full rounded-xl border px-3 py-2" value={analyticsForm.account_id} onChange={(e) => setAnalyticsForm({ ...analyticsForm, account_id: e.target.value })}>
                  {primaryAccounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
                </select>
                <input className="w-full rounded-xl border px-3 py-2" type="number" value={analyticsForm.interval_minutes} onChange={(e) => setAnalyticsForm({ ...analyticsForm, interval_minutes: Number(e.target.value) })} />
                <button className="rounded-xl bg-slate-900 px-4 py-2 text-white" type="submit">创建任务</button>
              </form>
            </Card>
            <div className="space-y-6">
              <Card title="监控任务">
                <div className="space-y-4">
                  {analyticsTasks.map((task) => (
                    <div key={task.id} className="rounded-2xl border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="font-semibold">{task.account_id}</div>
                          <div className="text-sm text-slate-500">间隔 {task.interval_minutes} 分钟</div>
                          <div className="mt-1 text-xs text-slate-500">状态 {task.task_status} · {task.enabled ? "启用" : "停用"}</div>
                          <div className="mt-1 text-xs text-slate-500">最近执行 {task.last_run_at ? new Date(task.last_run_at).toLocaleString() : "无"}</div>
                          {task.last_error ? <div className="mt-2 text-xs text-rose-600">{task.last_error}</div> : null}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => toggleAnalyticsTask(task)}>
                            {task.enabled ? "停用" : "启用"}
                          </button>
                          <button className="rounded-lg border px-3 py-1 text-sm" onClick={() => runAnalyticsTaskNow(task)}>立即执行</button>
                          <button className="rounded-lg border px-3 py-1 text-sm text-rose-600" onClick={() => deleteTask("analytics", task.id)}>删除任务</button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
              <Card title="监控快照">
                <div className="space-y-4">
                  {analyticsSnapshots.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-slate-200 p-4">
                      <div className="font-semibold">{item.nickname || item.account_id}</div>
                      <div className="mt-1 text-sm text-slate-500">粉丝 {item.follower_count} · 获赞 {item.liked_total} · 发帖 {item.post_total}</div>
                      <div className="mt-3 grid gap-2">
                        {item.posts.slice(0, 3).map((post) => (
                          <div key={post.id} className="rounded-xl bg-slate-50 px-3 py-2 text-sm">
                            {post.title || post.post_id} · 点赞 {post.like_count} · 评论 {post.comment_count}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        )}

        {tab === "devices" && (
          <Card title="设备列表">
            <div className="space-y-4">
              {devices.map((device) => (
                <div key={device.id} className="rounded-2xl border border-slate-200 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold">{device.device_name || device.device_id}</div>
                      <div className="mt-1 text-sm text-slate-500">{device.device_id} · {device.app_instance_id}</div>
                      <div className="mt-1 text-xs text-slate-500">状态 {device.status} · 版本 {device.app_version} · 最近心跳 {device.last_heartbeat_at ? new Date(device.last_heartbeat_at).toLocaleString() : "无"}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {tab === "logs" && (
          <Card title="审计日志">
            <div className="space-y-3">
              {logs.map((log) => (
                <div key={log.id} className="rounded-2xl border border-slate-200 p-4">
                  <div className="font-semibold">{log.message}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {log.log_type} · {log.operator_type}:{log.operator_id} · {log.target_type}:{log.target_id}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{new Date(log.created_at).toLocaleString()}</div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
