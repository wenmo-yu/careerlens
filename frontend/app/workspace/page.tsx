"use client";

import { ImportResultCard } from "@/components/import-result-card";
import { AssessmentCard } from "@/components/assessment-card";
import { ImportHub } from "@/components/import-hub";
import { CapabilityCards, ProfileModes } from "@/components/profile-enhancements";
import { CourseCatalog, LearningBoard, RoleSuggestions } from "@/components/learning-board";
import { CoverageCard, EvidenceTimeline, ProfileRadar, SkillMatrix } from "@/components/profile-insights";
import { ReportOverview, ScoreBreakdown } from "@/components/score-breakdown";
import { RunCenter } from "@/components/run-center";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import type { ReactNode } from "react";
import type { KnowledgeMode, LearningPlanStep } from "@/lib/api";
import { useWorkspace } from "@/lib/use-workspace";

export default function Home() {
  const {
    userId, setUserId, evidenceText, setEvidenceText, profile, setProfile, overview, evidenceList, jobTitle, setJobTitle, jdText, setJdText, weeklyHours, setWeeklyHours, analysis, setAnalysis, roleSuggestions, courses, savedJobs, savedJobTitle, setSavedJobTitle, report, setReport, chatInput, setChatInput, chat, setChat, knowledgeMode, setKnowledgeMode, wikiSources, setWikiSources, wikiSelection, setWikiSelection, wikiTitle, setWikiTitle, confirmWiki, setConfirmWiki, openedWiki, setOpenedWiki, memoryInput, setMemoryInput, proposal, setProposal, evaluation, telemetry, registrationSecret, setRegistrationSecret, issuedToken, deleteEvidenceId, setDeleteEvidenceId, accountDeletionConfirm, setAccountDeletionConfirm, auditEvents, busy, notice, setNotice, browserDraft, setBrowserDraft, selectedCaptureItems, setSelectedCaptureItems, latestRun, setLatestRun, importResult, setImportResult, tasksVersion, openRunResult, handleBuildProfile, handleJob, handleSaveJob, handleRecommendRoles, handleProgress, handleChat, loadWikiSources, handleWikiCompile, openWiki, handleReport, handleReportDownload, handleProposal, handleDecision, handleBilibili, handleWeibo, handleBrowserCapture, handleConfirmBrowserCapture, handleMedia, handleDocument, handleEvaluation, handleRegisterOwner, handleExport, handleLoadAudit, handleDeleteEvidence, handleDeleteAccount, skills,
  } = useWorkspace();

  return (
    <main className="site-page workspace-page">
      <SiteHeader active="workspace" />
      <nav className="workspace-subnav" aria-label="工作台模块">
        <span>WORKSPACE / 真实业务接口 · 虚构预填内容</span>
        <div><a href="#profile">职业画像</a><a href="#matching">岗位匹配</a><a href="#report">职业报告</a><a href="#copilot">Career Copilot</a><a href="#runs">后台任务</a><a href="#assessment">自我探索</a><a href="#quality">质量评测</a><a href="#privacy">数据控制</a></div>
      </nav>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">WORKSPACE / 真实业务接口 · 预填内容为虚构示例</p>
          <h1>职业工作台</h1>
          <p className="hero-copy">导入经历 → 构建画像 → 逐项匹配 → 生成报告。每个结论都能回到原始证据；操作会调用真实接口，不会替你编造已有能力。</p>
        </div>
        <div className="hero-metric" aria-label="当前状态">
          <span>当前用户</span>
          <strong>{userId}</strong>
          <p>{profile ? `${profile.count} 项画像` : "尚未构建画像"} · {evidenceList.length} 条证据</p>
        </div>
      </section>

      <div className="workspace-steps-wrap">
        <nav className="workspace-steps" aria-label="工作流程">
          <a href="#profile"><b>1</b><span><strong>导入与画像</strong><small>Evidence → Profile</small></span></a>
          <a href="#matching"><b>2</b><span><strong>岗位匹配</strong><small>JD → Match</small></span></a>
          <a href="#report"><b>3</b><span><strong>职业报告</strong><small>Report</small></span></a>
          <a href="#copilot"><b>4</b><span><strong>追问</strong><small>Copilot</small></span></a>
          <a href="#assessment"><b>5</b><span><strong>自我探索</strong><small>Optional</small></span></a>
        </nav>
      </div>

      {notice && <div className={`notice ${notice.kind}`} role="status">{notice.text}</div>}
      <section className="workspace" id="profile">
        <div className="section-heading">
          <div><span>01</span><h2>构建职业画像</h2></div>
          <p>先从简历、自述或导出内容建立 Evidence。</p>
        </div>
        {importResult && <ImportResultCard result={importResult} onDismiss={() => setImportResult(null)} onDeleteEvidence={(id) => setDeleteEvidenceId(id)} />}

        <div className="two-column">
          <form id="import-form" className="panel input-panel" onSubmit={handleBuildProfile}>
            <label>用户标识<input value={userId} disabled={busy !== null} onChange={(event) => {
              setUserId(event.target.value);
              setLatestRun(null);
              setImportResult(null);
              setProfile(null);
              setChat(null);
              setAnalysis(null);
              setReport(null);
              setProposal(null);
              setOpenedWiki(null);
              setWikiSources(null);
              setWikiSelection([]);
            }} required /></label>
            <label>个人经历与自述<textarea rows={9} value={evidenceText} onChange={(event) => setEvidenceText(event.target.value)} required /></label>
            <button disabled={busy !== null}>{busy === "profile" ? "正在构建…" : "导入并生成画像"}<span>↗</span></button>
          </form>
          <div className="panel profile-panel">
            <div className="panel-title"><h3>Structured Profile</h3><span>{profile ? `${profile.count} ITEMS` : "WAITING"}</span></div>
            {skills.length ? <div className="skill-list">{skills.map((skill) => (
              <article key={skill.id}>
                <div><strong>{skill.name}</strong><small>{skill.evidence_ids.length} 条证据</small></div>
                <LevelScale level={skill.level} />
                <span className="skill-meta">L{skill.level}<em>可信{confidenceBand(skill.confidence)}</em></span>
              </article>
            ))}</div> : (
              <Empty
                text="导入经历后，这里会显示带等级、证据条数与 Evidence ID 的技能画像。"
                action={<a className="empty-action" href="#import-form">填入第一段经历 ↑</a>}
              />
            )}
            {skills.length > 0 && <p className="profile-score-note">刻度是抽取器给出的等级（1–5）；可信度只分高/中/低三档，因为同分证据的细微差别不可信。两者都不是“具备该能力”的概率，请结合 Evidence 原文核对。</p>}
          </div>
        </div>
        {profile ? (
          <>
            <div className="insight-grid">
              <ProfileRadar profile={profile} />
              <CoverageCard overview={overview} />
              <SkillMatrix profile={profile} />
              <EvidenceTimeline evidence={evidenceList} />
            </div>
            <CapabilityCards profile={profile} evidence={evidenceList} />
          </>
        ) : (
          <div className="insight-placeholder">
            <strong>导入第一段经历后，这里会生成画像洞察</strong>
            <p>包括能力雷达、证据覆盖度、技能矩阵与证据时间线；每个条目都绑定可回看原文的 Evidence。能力卡只在有证据支撑时出现。</p>
          </div>
        )}
        <ProfileModes userId={userId} onNotice={(text) => setNotice({ kind: "ok", text })} />
        <ImportHub userId={userId} onNotice={(text) => setNotice({ kind: "ok", text })} />
        <div className="connector-strip">
          <div><span>IMPORT HUB / 用户主动提供</span><h3>从个人数据源继续补充证据</h3><p>只支持用户上传文件、平台导出文件与当前页手动采集；不读取 Cookie、不自动翻页、不后台爬取。点赞/收藏/关注只作兴趣线索，不会变成能力事实。</p></div>
          <label className="upload-card"><b>Bilibili Export</b><small>JSON · 视频标题 / 简介 / 字幕 / 标签</small><input type="file" accept="application/json,.json" onChange={handleBilibili} disabled={busy !== null} /><i>{busy === "bilibili" ? "导入中…" : "选择导出文件 ↗"}</i></label>
          <label className="upload-card"><b>Weibo Export</b><small>JSON / CSV · 正文 / 话题 / 转发 / 时间</small><input type="file" accept="application/json,text/csv,.json,.csv" onChange={handleWeibo} disabled={busy !== null} /><i>{busy === "weibo" ? "导入中…" : "选择导出文件 ↗"}</i></label>
          <label className="upload-card"><b>Browser Capture</b><small>B站 / 微博 / 抖音 / 掘金 / CSDN / 知乎 / 小红书 / GitHub · 发布/贡献=自报，互动=兴趣线索 · JSON</small><input type="file" accept="application/json,.json" onChange={handleBrowserCapture} disabled={busy !== null} /><i>{busy === "browser-preview" ? "读取中…" : "选择采集文件并核对 ↗"}</i></label>
          <label className="upload-card"><b>OCR / ASR</b><small>PNG / JPG / MP3 / WAV / MP4 / WEBM</small><input type="file" accept="image/*,audio/*,video/*" onChange={handleMedia} disabled={busy !== null} /><i>{busy === "media" ? "解析中…" : "选择媒体文件 ↗"}</i></label>
          <label className="upload-card"><b>文档 · PDF / Word .docx / 表格</b><small>PDF / DOCX / XLSX / TXT / MD / CSV · 保留页码与表格；扫描页需 OCR，旧 .doc 请另存为 .docx 或带文字层 PDF</small><input type="file" accept=".pdf,.docx,.xlsx,.txt,.md,.markdown,.csv,.tsv" onChange={handleDocument} disabled={busy !== null} /><i>{busy === "document" ? "解析中…" : "选择文档 ↗"}</i></label>
          <label className="upload-card"><b>HTML / 导出 ZIP</b><small>网页另存为 HTML、个人数据下载 ZIP · 只本地解析，不联网、不登录平台</small><input type="file" accept=".html,.htm,.zip" onChange={handleDocument} disabled={busy !== null} /><i>{busy === "document" ? "解析中…" : "选择导出文件 ↗"}</i></label>
        </div>
        {browserDraft && <div className="capture-review" aria-label="页面采集审核">
          <div className="capture-review-head">
            <div><span>REVIEW BEFORE IMPORT</span><h3>核对页面采集内容</h3><p>目标用户：{browserDraft.userId} · {browserDraft.capture.platform} / {browserDraft.capture.kind} · 已选 {selectedCaptureItems.length} / {browserDraft.capture.items.length} 条</p></div>
            <div className="capture-review-actions"><button type="button" className="secondary" onClick={() => setSelectedCaptureItems(browserDraft.capture.items.map((_, index) => index))}>全选</button><button type="button" className="secondary" onClick={() => setSelectedCaptureItems([])}>全不选</button></div>
          </div>
          <p className="capture-review-note">只导入勾选的条目。请核对内容确实来自自己的页面，且没有不希望保存的文字。发布内容按用户自报处理；点赞、收藏与关注仅用于兴趣线索。</p>
          <div className="capture-review-list">{browserDraft.capture.items.map((item, index) => <label key={`${item.url}-${index}`} className="capture-review-item">
            <input type="checkbox" checked={selectedCaptureItems.includes(index)} onChange={(event) => setSelectedCaptureItems((current) => event.target.checked ? [...current, index] : current.filter((value) => value !== index))} />
            <span><strong>{item.title || `条目 ${index + 1}`}</strong><small>{item.text.slice(0, 240)}</small><em>{item.url}</em></span>
          </label>)}</div>
          <div className="capture-review-actions"><button type="button" onClick={handleConfirmBrowserCapture} disabled={busy !== null || selectedCaptureItems.length === 0}>{busy === "browser-capture" ? "导入中…" : `确认导入 ${selectedCaptureItems.length} 条`}</button><button type="button" className="secondary" disabled={busy !== null} onClick={() => { setBrowserDraft(null); setSelectedCaptureItems([]); setNotice({ kind: "ok", text: "已取消，本次采集内容没有写入。" }); }}>取消</button></div>
        </div>}
        <div className={`memory-panel${proposal ? " has-proposal" : ""}`}>
          <div><span>HUMAN IN THE LOOP</span><h3>长期画像纠正</h3><p>模型只生成变更草案；只有你确认后，系统才把它作为新证据写入画像。</p></div>
          <form onSubmit={handleProposal}><textarea rows={3} value={memoryInput} onChange={(event) => setMemoryInput(event.target.value)} required /><button disabled={busy !== null}>{busy === "proposal" ? "解析中…" : "生成变更草案"}</button></form>
          {proposal && <div className={`proposal ${proposal.status}`}><b>{proposal.status === "pending" ? "等待确认" : proposal.status === "approved" ? "已写入" : "已拒绝"}</b>{proposal.changes.map((change, index) => <p key={`${change.name}-${index}`}><code>{change.action}</code> {change.category} · {change.name}</p>)}{proposal.status === "pending" && <div><button type="button" onClick={() => handleDecision(true)} disabled={busy !== null}>确认写入</button><button type="button" className="secondary" onClick={() => handleDecision(false)} disabled={busy !== null}>拒绝</button></div>}</div>}
        </div>
      </section>

      <section className="workspace dark-section" id="matching">
        <div className="section-heading light">
          <div><span>02</span><h2>岗位逐项匹配</h2></div>
          <p>逐项识别岗位要求，与带证据引用的职业画像对照。</p>
        </div>
        <form className="jd-form" onSubmit={handleJob}>
          <div className="jd-fields">
            <label>岗位名称<input value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} required /></label>
            <label className="hours">每周学习小时<input type="number" min="1" max="80" value={weeklyHours} onChange={(event) => setWeeklyHours(Number(event.target.value))} /></label>
            <label className="wide">岗位描述<textarea rows={6} value={jdText} onChange={(event) => setJdText(event.target.value)} required /></label>
            <button disabled={busy !== null}>{busy === "job" ? "分析中…" : "分析匹配度"}</button>
          </div>
          <div className="score-card">
            <span>RULE-BASED MATCH</span>
            <strong>{analysis ? <>{analysis.score}<small>%</small></> : <span className="score-empty">待分析</span>}</strong>
            <p>{analysis?.report.recommendation ?? "完成画像后提交 JD"}</p>
            {analysis && <small className="score-disclaimer">
              规则匹配分，不是录用概率
              {analysis.report.required_gap_count !== undefined && ` · 必需缺口 ${analysis.report.required_gap_count} 项`}
            </small>}
          </div>
        </form>
        {analysis && <ScoreBreakdown analysis={analysis} />}
        <div className="jd-save-row">
          <label>保存当前 JD 用于对比<input value={savedJobTitle} placeholder={jobTitle || "岗位名称"} onChange={(event) => setSavedJobTitle(event.target.value)} /></label>
          <button type="button" onClick={handleSaveJob} disabled={busy !== null}>保存 JD</button>
          <span>已保存 {savedJobs.length} 份 · 最多对比 3 份</span>
        </div>
        <div className="role-actions">
          <button type="button" onClick={handleRecommendRoles} disabled={busy !== null}>{busy === "roles" ? "生成中…" : "查看相邻职业方向"}</button>
          <small>方向来自本地教学模板；理由必须回到真实技能与证据，不使用人格测评结果排序。</small>
        </div>
        <RoleSuggestions rows={roleSuggestions} />
        {analysis && <div className="match-grid">
          <div className="match-table">
            <div className="table-row head"><span>岗位要求</span><span>状态</span><span>证据</span></div>
            {analysis.matches.map((match) => <div className="table-row" key={match.name}>
              <span>{match.name}<small>{match.priority === "preferred" ? "加分项" : "必需"}</small></span>
              <span className={`pill ${match.status}`}>{match.status}</span>
              <span>{match.evidence_ids.length ? `${match.evidence_ids.length} 条` : "暂无"}</span>
            </div>)}
          </div>
          <div className="path-card"><h3>Gap → Learning Path</h3><p className="path-disclaimer">按缺口、现有等级与每周时间排序的规则式计划；实践成果可作为下一轮 Evidence。</p>{analysis.learning_path.length ? analysis.learning_path.map((step) => <article key={step.skill}><b>0{step.stage}</b><div><strong>{step.skill}</strong><p>{step.goal}</p><small>{step.start_week ? `第 ${step.start_week} 周起 · ` : ""}预计 {step.weeks} 周{step.estimated_hours ? ` / ${step.estimated_hours} 小时` : ""}</small></div></article>) : <Empty text="当前没有识别到明确缺口。" />}</div>
        </div>}
        {analysis && <LearningBoard steps={analysis.learning_path as LearningPlanStep[]} onProgress={handleProgress} />}
        <CourseCatalog courses={courses} />
      </section>

      <section className="workspace report-section" id="report">
        <div className="section-heading">
          <div><span>03</span><h2>完整职业报告</h2></div>
          <p>将画像、岗位证据、能力缺口和学习路线固化为可追溯版本。</p>
        </div>
        <div className="report-shell">
          <div className="report-intro">
            <span>REPORT BUILDER</span>
            <h3>{report?.title ?? "等待岗位分析"}</h3>
            <p>{report?.content.executive_summary ?? "先完成目标 JD 分析，再生成八个固定章节的职业报告。模型只负责在证据边界内润色；不可用时自动生成确定性版本。"}</p>
            <div className="report-actions">
              <button type="button" onClick={handleReport} disabled={busy !== null || !analysis}>{busy === "report" ? "生成中…" : report ? "生成新版本" : "生成职业报告"}</button>
              <button type="button" className="secondary" onClick={handleReportDownload} disabled={busy !== null || !report}>{busy === "report-download" ? "导出中…" : "下载 Markdown"}</button>
            </div>
            {report && <div className="report-meta"><span>VERSION {report.version}</span><span>{report.model_diagnostics.provider} / {report.model_diagnostics.model}</span><span>{report.content.referenced_evidence_ids.length} EVIDENCE</span>{report.is_stale && <span className="stale">STALE</span>}</div>}
          </div>
          <div className="report-preview">
            {report ? <>
              <article><b>01</b><div><span>个人职业画像</span><strong>{report.content.core_capabilities.slice(0, 4).map((item) => item.name).join(" · ") || "等待画像"}</strong></div></article>
              <article><b>02</b><div><span>推荐就业方向</span><strong>{report.content.career_direction.primary_role} · {report.content.career_direction.match_score}%</strong></div></article>
              <article><b>03</b><div><span>能力缺口</span><strong>{report.content.skill_gaps.map((item) => item.name).join(" · ") || "当前 JD 无明确缺口"}</strong></div></article>
              <article><b>04</b><div><span>下一步行动</span><strong>{report.content.action_plan[0]}</strong></div></article>
              <blockquote>{report.content.interview_pitch}</blockquote>
            </> : (
              <Empty
                text="报告会保留版本号、Provider 诊断与 Evidence 引用。先完成一次岗位匹配，再生成报告。"
                action={<a className="empty-action" href="#matching">去岗位匹配 ↓</a>}
              />
            )}
          </div>
        </div>
        {report && <ReportOverview content={report.content as unknown as Record<string, unknown>} />}
      </section>

      <section className="workspace copilot" id="copilot">
        <div className="section-heading"><div><span>04</span><h2>Career Copilot</h2></div><p>追问结论，直接查看引用证据。</p></div>
        <details className="wiki-controls">
          <summary>从证据编译 Wiki 专题</summary>
          <form onSubmit={handleWikiCompile}>
            <label>专题标题<input value={wikiTitle} maxLength={255} onChange={(event) => setWikiTitle(event.target.value)} required /></label>
            <label className="run-confirm"><input type="checkbox" checked={confirmWiki}
              onChange={(event) => setConfirmWiki(event.target.checked)} /> 先创建任务，确认后编译</label>
            <button type="button" className="secondary" disabled={busy !== null} onClick={() => loadWikiSources(0, true)}>加载证据</button>
            {wikiSources?.userId === userId && <>
              <p>已选 {wikiSelection.length} / 50 条证据。{wikiSources.items.length === 0 && "本页没有证据。"}</p>
              <div className="wiki-source-list">
                {wikiSources.items.map((item) => <label key={item.id}>
                  <input type="checkbox" checked={wikiSelection.includes(item.id)}
                    disabled={wikiSelection.length >= 50 && !wikiSelection.includes(item.id)}
                    onChange={(event) => setWikiSelection((current) => event.target.checked
                      ? [...current, item.id] : current.filter((id) => id !== item.id))} />
                  <span>{item.source_name} · {item.content.slice(0, 100)}</span>
                </label>)}
              </div>
              <div className="report-actions">
                {wikiSources.offset > 0 && <button type="button" className="secondary" disabled={busy !== null} onClick={() => loadWikiSources(wikiSources.offset - 50)}>上一页</button>}
                {wikiSources.items.length === 50 && <button type="button" className="secondary" disabled={busy !== null} onClick={() => loadWikiSources(wikiSources.offset + 50)}>下一页</button>}
                <button disabled={busy !== null || !wikiSelection.length}>{busy === "wiki-compile" ? "编译中…" : "编译 Wiki"}</button>
              </div>
            </>}
          </form>
        </details>
        {openedWiki?.userId === userId && <article className="wiki-controls">
          <h3>{openedWiki.page.title} · v{openedWiki.page.version}</h3>
          <p className="wiki-markdown">{openedWiki.page.content}</p>
          <p>证据 ID：{openedWiki.page.chunk_refs.join(" · ")}</p>
        </article>}
        <label className="knowledge-mode">检索模式
          <select value={knowledgeMode} onChange={(event) => setKnowledgeMode(event.target.value as KnowledgeMode)}>
            <option value="rag">RAG · 原始证据</option>
            <option value="wiki">Wiki · 已编译专题</option>
            <option value="hybrid">混合 · 证据和专题</option>
          </select>
        </label>
        <div className="chat-shell">
          <div className="chat-context"><span>当前用户</span><strong>{userId}</strong><p>{skills.slice(0, 4).map((item) => item.name).join(" · ") || "等待画像"}</p></div>
          <div className="conversation">
            {chat ? <>
              {chat.messages.map((message, index) => (
                <div key={`${message.created_at ?? "msg"}-${index}`} className={`bubble ${message.role === "user" ? "user" : "agent"}`}>
                  {message.role === "assistant" && <small>CAREERLENS · {message.intent ?? chat.intent}</small>}
                  <p>{message.content}</p>
                  {message.role === "assistant" && index === chat.messages.length - 1 && <div className="retrieval-badges"><span>{chat.model.provider} / {chat.model.model}</span><span>{chat.retrieval.backend}</span><span>{chat.retrieval.fusion}</span><span>{chat.retrieval.reranker}</span>{chat.model.fallback && <span className="fallback">model fallback</span>}{chat.retrieval.fallback && <span className="fallback">retrieval fallback</span>}</div>}
                </div>
              ))}
              {chat.evidence.length > 0 && <div className="evidence-stack">
                <b>引用来源 · {chat.retrieval.mode ?? "rag"}</b>
                {chat.evidence.map((item) => item.source_kind === "wiki"
                  ? <details key={item.page_id}><summary>{item.title}<span>Wiki</span></summary>
                    <p>{item.content}</p>
                    <button type="button" className="secondary" disabled={busy !== null} onClick={() => openWiki(item.slug)}>打开 Wiki 全文</button>
                    <p>证据 ID：{item.chunk_refs.join(" · ")}</p>
                  </details>
                  : <details key={item.evidence_id}><summary>{item.source_name}<span>RAG</span></summary>
                    <p>{item.content}</p><code>{item.evidence_id}</code>
                  </details>)}
              </div>}
            </> : (
              <Empty
                text="Copilot 只回答与你的证据有关的问题。可以先从这句开始。"
                action={
                  <button type="button" className="empty-action" onClick={() => setChatInput("为什么认为我适合 Agent 开发？")}>
                    用这个问题开始 ↑
                  </button>
                }
              />
            )}
            <form className="chat-input" onSubmit={handleChat}><input value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="询问你的职业画像…" required /><button aria-label="发送" disabled={busy !== null}>↑</button></form>
          </div>
        </div>
      </section>

      <RunCenter key={`${userId}:${latestRun?.id ?? ""}:${tasksVersion}`} userId={userId}
        latest={latestRun} refresh={tasksVersion} onOpen={openRunResult} />

      <section className="workspace assessment-section" id="assessment">
        <AssessmentCard userId={userId} onNotice={(text) => setNotice({ kind: "ok", text })} />
      </section>

      <section className="workspace quality-section" id="quality">
        <div className="section-heading">
          <div><span>05</span><h2>质量评测与观测</h2></div>
          <p>使用人工标注基准衡量抽取、检索和匹配，不让模型自己给自己打分。</p>
        </div>
        <div className="quality-grid">
          <div className="quality-main">
            <div className="quality-title"><div><span>CONTINUOUS REGRESSION GATE</span><h3>{evaluation?.dataset_name ?? "等待首次评测"}</h3></div><button type="button" onClick={handleEvaluation} disabled={busy !== null}>{busy === "evaluation" ? "评测中…" : "运行质量门禁"}</button></div>
            <div className="metric-grid">
              <Metric label="Profile Extraction F1" value={evaluation?.profile_extraction_f1} />
              <Metric label={`Evidence Recall@${evaluation?.metrics.recall_k ?? "K"}`} value={evaluation?.evidence_recall_at_k} />
              <Metric label="Supported Claim Rate" value={evaluation?.supported_claim_rate} />
              <Metric label="Requirement Matching F1" value={evaluation?.requirement_matching_f1} />
            </div>
            {evaluation?.details.regression && <div className={`gate-strip ${evaluation.details.regression.status}`}><strong>{evaluation.details.regression.status === "passed" ? "PASS" : "FAIL"}</strong><span>{evaluation.details.regression.status === "passed" ? "全部核心指标达到冻结基线" : `${evaluation.details.regression.failures.length} 项指标未达到最低阈值`}</span></div>}
            <p className="sample-note">{evaluation ? `${evaluation.metrics.case_count} 个场景 · ${evaluation.metrics.query_count} 个检索问题 · ${evaluation.metrics.claim_count} 个画像结论` : "开发基准用于持续回归；真实业务指标需另行扩充脱敏人工标注集后再引用。"} {evaluation?.dataset_name.includes("dev-benchmark") && "当前为合成开发基准，不代表真实用户准确率。"}</p>
          </div>
          <aside className="telemetry-card">
            <span>MODEL OBSERVABILITY</span><h3>调用健康度</h3>
            <dl><div><dt>请求数</dt><dd>{telemetry?.request_count ?? 0}</dd></div><div><dt>成功率</dt><dd>{Math.round((telemetry?.success_rate ?? 0) * 100)}%</dd></div><div><dt>平均延迟</dt><dd>{telemetry?.average_latency_ms ?? 0}<small> ms</small></dd></div><div><dt>P95 延迟</dt><dd>{telemetry?.p95_latency_ms ?? 0}<small> ms</small></dd></div><div><dt>Token</dt><dd>{(telemetry?.prompt_tokens ?? 0) + (telemetry?.completion_tokens ?? 0)}</dd></div><div><dt>估算成本</dt><dd>${(telemetry?.estimated_cost_usd ?? 0).toFixed(4)}</dd></div></dl>
            <p>成本由环境变量中的每百万 Token 单价估算；OTLP Span 只记录模型、耗时、Token 和状态，不记录 Prompt、API Key 或 Evidence 原文。</p>
          </aside>
        </div>
      </section>

      <section className="workspace privacy-section" id="privacy">
        <div className="section-heading light">
          <div><span>06</span><h2>隐私与数据控制</h2></div>
          <p>Token 只返回一次；导出和删除会留下不包含原文的审计记录。</p>
        </div>
        <div className="privacy-grid">
          <article><span>01 / ACCESS</span><h3>Owner Token</h3><p>生产环境开启强制鉴权后，用 Registration Secret 初始化第一个 Owner Token。</p><input type="password" value={registrationSecret} onChange={(event) => setRegistrationSecret(event.target.value)} placeholder="Registration Secret（本地可留空）" /><button type="button" onClick={handleRegisterOwner} disabled={busy !== null}>{busy === "register" ? "创建中…" : "创建并启用 Token"}</button>{issuedToken && <code className="token-output">{issuedToken}</code>}</article>
          <article><span>02 / PORTABILITY</span><h3>导出我的数据</h3><p>导出 Evidence、画像、JD 分析、职业报告、画像纠正和审计日志，不包含 Token 哈希。</p><button type="button" onClick={handleExport} disabled={busy !== null}>{busy === "export" ? "导出中…" : "下载 JSON 数据副本"}</button></article>
          <article><span>03 / ERASURE</span><h3>删除数据</h3><p>可删除单条 Evidence；永久删除账号会同时清理数据库、向量、对话状态和全部 Token。</p><input value={deleteEvidenceId} onChange={(event) => setDeleteEvidenceId(event.target.value)} placeholder="Evidence ID" /><button type="button" className="danger" onClick={handleDeleteEvidence} disabled={busy !== null || !deleteEvidenceId}>{busy === "delete" ? "删除中…" : "删除 Evidence"}</button><div className="erasure-divider" /><input value={accountDeletionConfirm} onChange={(event) => setAccountDeletionConfirm(event.target.value)} placeholder={`输入 ${userId} 确认永久删除`} /><button type="button" className="danger" onClick={handleDeleteAccount} disabled={busy !== null || accountDeletionConfirm !== userId}>{busy === "delete-account" ? "正在永久删除…" : "永久删除账号"}</button></article>
          <article className="audit-card"><span>04 / AUDIT</span><h3>最近操作</h3><button type="button" className="secondary" onClick={handleLoadAudit} disabled={busy !== null}>{busy === "audit" ? "读取中…" : "刷新审计日志"}</button>{auditEvents.length ? <div>{auditEvents.map((event) => <p key={event.id}><b>{event.action}</b><small>{event.resource_id ?? event.resource_type}</small></p>)}</div> : <p>尚未读取审计事件。</p>}</article>
        </div>
      </section>

      <SiteFooter />
    </main>
  );
}

function Empty({ text, action }: { text: string; action?: ReactNode }) {
  return <div className="empty"><span>＋</span><p>{text}</p>{action}</div>;
}

/** Skill level as five discrete marks: a 1/5 and a 5/5 must never look alike. */
function LevelScale({ level }: { level: number }) {
  return (
    <span className="level-scale" role="img" aria-label={`等级 ${level} / 5`}>
      {[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= level ? "on" : ""} />)}
    </span>
  );
}

const confidenceBand = (value: number) => (value >= .9 ? "高" : value >= .8 ? "中" : "低");

function Metric({ label, value }: { label: string; value?: number }) {
  return <article><span>{label}</span><strong>{value === undefined ? "—" : Math.round(value * 100)}<small>{value === undefined ? "" : "%"}</small></strong><i><b style={{ width: `${(value ?? 0) * 100}%` }} /></i></article>;
}
