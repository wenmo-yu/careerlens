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

    $chat = Invoke-Json POST "$apiRoot/chat" @{
        user_id = $UserId
        message = "结合我的证据和目标岗位，给出本周最优先行动。"
        thread_id = "docker-smoke-thread"
        job_analysis_id = $job.id
    }
    Assert-True (-not [string]::IsNullOrWhiteSpace($chat.answer)) "LangGraph chat"

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
