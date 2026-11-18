class Brewcat < Formula
  desc "Visual catalog of Homebrew packages, skills and MCP servers for devs and gamers"
  homepage "https://github.com/1985epma/homebrew-brewcat"
  url "https://github.com/1985epma/homebrew-brewcat/archive/refs/tags/v0.2.1.tar.gz"
  sha256 "969c75a7aff9c691a5d5e652fff7d44ad0d78fdf9e3b5577e80752ea0e95c991"
  license "MIT"

  depends_on "rust" => :build

  def install
    system "cargo", "install", *std_cargo_args
  end

  def caveats
    <<~EOS
      Run the app with:
        brewcat

      On Linux the window needs a graphical session and OpenGL/EGL or Vulkan drivers.
      The command line (brewcat --help) works without them.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/brewcat --version")
    # These read the built-in catalog only; none of them runs brew.
    assert_match "Git Pro", shell_output("#{bin}/brewcat kits --json")
    assert_match "117-labs", shell_output("#{bin}/brewcat profiles")
  end
end
