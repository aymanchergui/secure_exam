$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path

. "$here\config.local.ps1"

Set-Location $here

go run .
