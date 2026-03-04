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

    # Install all lacp-* scripts from bin/
    Dir[libexec/"bin/lacp-*"].each do |script|
      cmd = File.basename(script)
      (bin/cmd).write_env_script(libexec/"bin/#{cmd}", {})
    end

    # Install the main router
    %w[
      lacp
    ].each do |cmd|
      (bin/cmd).write_env_script(libexec/"bin/#{cmd}", {})
    end
  end

  test do
    output = shell_output("#{bin}/lacp-route --task 'homebrew test task' --json")
    assert_match "route", output
  end
end
