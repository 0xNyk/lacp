class Lacp < Formula
  desc "Local Agent Control Plane for Claude/Codex"
  homepage "https://github.com/0xNyk/lacp"
  license "MIT"
  head "https://github.com/0xNyk/lacp.git", branch: "main"

  depends_on "bash"
  depends_on "jq"
  depends_on "python@3.11"
  depends_on "ripgrep"

  def install
    libexec.install Dir["*"]

    %w[
      lacp
      lacp-install
      lacp-onboard
      lacp-bootstrap
      lacp-verify
      lacp-doctor
      lacp-knowledge-doctor
      lacp-mode
      lacp-status-report
      lacp-route
      lacp-sandbox-run
      lacp-remote-setup
      lacp-remote-smoke
      lacp-report
      lacp-canary
      lacp-auto-rollback
      lacp-schedule-health
      lacp-policy-pack
      lacp-release-prepare
      lacp-cache-audit
      lacp-cache-guard
      lacp-skill-audit
      lacp-skill-factory
      lacp-adopt-local
      lacp-unadopt-local
      lacp-release-gate
      lacp-pr-preflight
      lacp-harness-validate
      lacp-harness-run
      lacp-browser-evidence-validate
      lacp-orchestrate
      lacp-worktree
      lacp-swarm
      lacp-migrate
      lacp-incident-drill
      lacp-workflow-run
      lacp-test
    ].each do |cmd|
      (bin/cmd).write_env_script(libexec/"bin/#{cmd}", {})
    end
  end

  test do
    output = shell_output("#{bin}/lacp-route --task 'homebrew test task' --json")
    assert_match "route", output
  end
end
