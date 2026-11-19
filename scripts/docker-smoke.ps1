[CmdletBinding()]
param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$McpUrl = "http://localhost:8001/mcp",
    [string]$UserId = "docker-smoke-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())",
    [switch]$KeepData
)

$ErrorActionPreference = "Stop"
$apiRoot = "$($BaseUrl.TrimEnd('/'))/api/v1"
$headers = @{}
$createdUser = $false

function Invoke-Json {
    param(
        [Parameter(Mandatory)][ValidateSet("GET", "POST", "DELETE")][string]$Method,
        [Parameter(Mandatory)][string]$Uri,
        [object]$Body
    )

    $arguments = @{
        Method = $Method
        Uri = $Uri
        Headers = $headers
    }
    if ($null -ne $Body) {
        $arguments.ContentType = "application/json"
        $arguments.Body = $Body | ConvertTo-Json -Depth 12
    }
    Invoke-RestMethod @arguments
}

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) {
        throw "Smoke test assertion failed: $Message"
    }
}

function Wait-Run {
    param([string]$RunId)

    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        $state = Invoke-Json GET "$apiRoot/runs/${RunId}?user_id=$UserId"
        if ($state.status -eq "succeeded") { return $state }
        if ($state.status -in @("failed", "cancelled")) {
            throw "Background task '$($state.operation)' ended as $($state.status): $($state.error_code)"
        }
        Start-Sleep -Milliseconds 300
    }
    throw "Timed out waiting for background task"
}

try {
    $live = Invoke-RestMethod "$BaseUrl/health/live"
    $ready = Invoke-RestMethod "$BaseUrl/health/ready"
    Assert-True ($live.status -eq "ok") "API liveness"
    Assert-True ($ready.status -eq "ok") "API readiness"
    Assert-True ($ready.checks.database -eq "ok") "PostgreSQL readiness"
    Assert-True ($ready.checks.qdrant -eq "ok") "Qdrant readiness"

    try {
        Invoke-WebRequest -Method Post -Uri $McpUrl `
            -ContentType "application/json" `
            -Headers @{ Accept = "application/json, text/event-stream" } `
            -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}' `
            -UseBasicParsing | Out-Null
        throw "MCP accepted an unauthenticated request"
    }
    catch {
        $statusCode = [int]$_.Exception.Response.StatusCode
        if ($statusCode -ne 401) { throw }
    }

    $registration = Invoke-Json POST "$apiRoot/auth/register" @{
        user_id = $UserId
        name = "docker-smoke"
    }
    $createdUser = $true
    $headers = @{ Authorization = "Bearer $($registration.token)" }

    $evidence = Invoke-Json POST "$apiRoot/evidence/text" @{
        user_id = $UserId
        source_type = "project"
        source_name = "docker-smoke"
        content = "我使用 Python、FastAPI、PostgreSQL、Qdrant、LangGraph 和 Docker 构建了带混合检索与证据引用的职业规划 RAG 系统，并负责测试和部署。"
    }
    Assert-True ($evidence.count -ge 1) "evidence ingestion"
    $secondImport = Invoke-Json POST "$apiRoot/evidence/text" @{
        user_id = $UserId
        source_type = "project"
        source_name = "docker-smoke-copy"
        content = $evidence.items[0].content
    }
    Assert-True ($secondImport.items[0].id -eq $evidence.items[0].id) "evidence deduplication"

    $form = [System.Net.Http.MultipartFormDataContent]::new()
    try {
        $form.Add([System.Net.Http.StringContent]::new($UserId), "user_id")
        $form.Add([System.Net.Http.StringContent]::new("Skill,Level`nFastAPI,Advanced"),
            "upload", "skills.csv")
        $source = Invoke-RestMethod -Method Post -Uri "$apiRoot/evidence/file" `
            -Headers $headers -Body $form
    }
    finally {
        $form.Dispose()
    }
    Assert-True ($source.count -eq 1) "structured document upload"
    $export = Invoke-Json GET "$apiRoot/privacy/$UserId/export"
    Assert-True (@($export.source_documents).Count -eq 1) "source document persisted"
    Assert-True ($export.parsed_blocks[0].evidence_id -eq $source.items[0].id) "parsed block lineage"
    $profile = Invoke-Json POST "$apiRoot/profiles/$UserId/rebuild" @{}
    Assert-True ($profile.count -ge 1) "profile rebuild"

    $job = Invoke-Json POST "$apiRoot/jobs/analyze" @{
        user_id = $UserId
        title = "AI Agent Backend Engineer"
        jd_text = "负责 Python 和 FastAPI 后端开发，使用 LangGraph 构建智能体工作流，熟悉 RAG、向量数据库 Qdrant、Docker、Kubernetes 和自动化测试。"
        weekly_hours = 8
    }
    Assert-True (@($job.requirements).Count -ge 1) "job requirement extraction"

    $report = Invoke-Json POST "$apiRoot/reports" @{
        user_id = $UserId
        job_analysis_id = $job.id
    }
    Assert-True (-not [string]::IsNullOrWhiteSpace($report.markdown)) "career report generation"

    $headers["Idempotency-Key"] = "smoke-background-report"
    $reportInput = @{
        user_id = $UserId
        operation = "report"
        input = @{ job_analysis_id = $job.id }
    }
    $background = Invoke-Json POST "$apiRoot/runs" $reportInput
    $replay = Invoke-Json POST "$apiRoot/runs" $reportInput
    $headers.Remove("Idempotency-Key")
    Assert-True ($background.id -eq $replay.id) "background idempotency"
    $saved = Wait-Run $background.id
    Assert-True ($saved.result.version -eq ($report.version + 1)) "one background report version"
    $streamHeaders = @{ Authorization = $headers.Authorization; "Last-Event-ID" = "2" }
    $progress = Invoke-WebRequest -Uri "$apiRoot/runs/$($saved.id)/stream?user_id=$UserId" `
        -Headers $streamHeaders -TimeoutSec 10
    Assert-True ($progress.Content -match "run.succeeded") "SSE progress resume"

    $queuedWiki = Invoke-Json POST "$apiRoot/runs" @{
        user_id = $UserId
        operation = "wiki_compile"
        requires_confirmation = $true
        input = @{ slug = "background-topic"; title = "FastAPI"; evidence_ids = @($evidence.items[0].id) }
    }
    Assert-True ($queuedWiki.status -eq "waiting_confirmation") "approval gate"
    $approved = Invoke-Json POST "$apiRoot/runs/$($queuedWiki.id)/decision?user_id=$UserId" @{
        approve = $true
    }
    Assert-True ($approved.confirmation -eq "approved") "explicit approval decision"
    $savedWiki = Wait-Run $queuedWiki.id
    Assert-True ($savedWiki.result.wiki_slug -eq "background-topic") "Wiki worker and verifier"

    $queuedCancel = Invoke-Json POST "$apiRoot/runs" @{
        user_id = $UserId
        operation = "job_analysis"
        requires_confirmation = $true
        input = @{ title = "Backend"; jd_text = "Python and FastAPI required." }
    }
    $cancelled = Invoke-Json POST "$apiRoot/runs/$($queuedCancel.id)/cancel?user_id=$UserId"
    Assert-True ($cancelled.status -eq "cancelled") "cancel pending work"

    $chat = Invoke-Json POST "$apiRoot/chat" @{
        user_id = $UserId
        message = "结合我的证据和目标岗位，给出本周最优先行动。"
        thread_id = "$UserId-thread"
        job_analysis_id = $job.id
    }
    Assert-True (-not [string]::IsNullOrWhiteSpace($chat.answer)) "LangGraph chat"

    $wiki = Invoke-Json POST "$apiRoot/wiki/compile" @{
        user_id = $UserId
        slug = "smoke-topic"
        title = "FastAPI skills"
        evidence_ids = @($source.items[0].id)
    }
    Assert-True ($wiki.page.version -eq 1) "compile Wiki page"
    foreach ($mode in @("rag", "wiki", "hybrid")) {
        $reply = Invoke-Json POST "$apiRoot/chat" @{
            user_id = $UserId
            message = "Show the evidence for FastAPI"
            thread_id = $chat.thread_id
            mode = $mode
        }
        Assert-True ($reply.retrieval.mode -eq $mode) "switch to $mode without rebuilding"
        if ($mode -ne "rag") {
            Assert-True (@($reply.evidence.source_kind) -contains "wiki") "$mode Wiki hit"
        }
    }
    $deletion = Invoke-Json DELETE "$apiRoot/evidence/$($source.items[0].id)"
    Assert-True ($deletion.removed_wiki_pages -eq 1) "delete dependent Wiki page"

    $query = [Uri]::EscapeDataString("FastAPI Qdrant")
    $search = Invoke-Json GET "$apiRoot/evidence/search?user_id=$UserId&query=$query&limit=5"
    Assert-True (@($search.items).Count -ge 1) "hybrid retrieval results"
    Assert-True ($search.retrieval.backend -eq "qdrant") "Qdrant retrieval backend"

    $benchmark = Invoke-Json POST "$apiRoot/evaluation/regression/benchmark" @{}
    Assert-True ($benchmark.status -eq "passed") "regression benchmark"

    $mcpHeaders = @{
        Authorization = "Bearer $($registration.token)"
        Accept = "application/json, text/event-stream"
    }
    $mcpBody = @{
        jsonrpc = "2.0"
        id = 1
        method = "initialize"
        params = @{
            protocolVersion = "2025-06-18"
            capabilities = @{}
            clientInfo = @{ name = "docker-smoke"; version = "1.0" }
        }
    } | ConvertTo-Json -Depth 10
    $mcp = Invoke-WebRequest -Method Post -Uri $McpUrl -ContentType "application/json" `
        -Headers $mcpHeaders -Body $mcpBody -UseBasicParsing
    Assert-True ($mcp.StatusCode -eq 200 -and $mcp.Content -match "serverInfo") "authenticated MCP initialize"

    [pscustomobject]@{
        status = "passed"
        user_id = $UserId
        evidence_count = $evidence.count
        profile_items = $profile.count
        requirements = @($job.requirements).Count
        report_id = $report.id
        chat_answer_chars = $chat.answer.Length
        retrieval_backend = $search.retrieval.backend
        regression = $benchmark.status
        mcp = "authenticated"
    } | Format-List
}
finally {
    if ($createdUser -and -not $KeepData) {
        try {
            $receipt = Invoke-Json DELETE "$apiRoot/privacy/$UserId" $null
            Write-Host "Smoke data deleted; receipt: $($receipt.receipt_id)"
        }
        catch {
            Write-Warning "Could not clean up smoke user '$UserId': $($_.Exception.Message)"
        }
    }
}
