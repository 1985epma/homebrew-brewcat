class Brewcat < Formula
  desc "Visual catalog of Homebrew packages, skills and MCP servers for devs and gamers"
  homepage "https://github.com/1985epma/homebrew-brewcat"
  url "https://github.com/1985epma/homebrew-brewcat/archive/refs/tags/v0.1.2.7.1.tar.gz"
  sha256 "14a32fd508a447e36923b4490bdbc793c1b80e64f533c64395dda4ef9607ccab"
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
