class Lacp < Formula
  desc "Local Agent Control Plane — harness, memory, and safety for AI coding agents"
  homepage "https://github.com/0xNyk/lacp"
  license "MIT"
  head "https://github.com/0xNyk/lacp.git", branch: "main"

  depends_on "bash"
  depends_on "jq"
  depends_on "python@3.11"
  depends_on "ripgrep"

  def install
    libexec.install Dir["*"]

    Dir[libexec/"bin/lacp*"].each do |f|
      cmd = File.basename(f)
      next if cmd.start_with?("__")
      (bin/cmd).write_env_script(libexec/"bin/#{cmd}", {})
    end
  end

  test do
    output = shell_output("#{bin}/lacp-route --task 'homebrew test task' --json")
    assert_match "route", output
    assert_match "lacp", shell_output("#{bin}/lacp help")
    assert_match "total", shell_output("#{bin}/lacp tools --text")
  end
end
