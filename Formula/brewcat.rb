class Brewcat < Formula
  desc "Visual catalog of Homebrew packages, skills and MCP servers for devs and gamers"
  homepage "https://github.com/1985epma/homebrew-brewcat"
  url "https://github.com/1985epma/homebrew-brewcat/archive/refs/tags/v0.1.2.7.1.tar.gz"
  sha256 "f5affab2a18b645ec06119ca598cdf9876a736dcb4af2a5aa01e6a2e0db1375e"
  license "MIT"

  depends_on "python-tk"

  def install
    libexec.install Dir["*.py"], "assets"
    (bin/"brewcat").write <<~SH
      #!/bin/bash
      exec "#{HOMEBREW_PREFIX}/bin/python3" "#{libexec}/app.py" "$@"
    SH
  end

  def caveats
    <<~EOS
      Run the app with:
        brewcat
    EOS
  end

  test do
    ENV.prepend_path "PYTHONPATH", libexec
    system "#{HOMEBREW_PREFIX}/bin/python3", "-c", "import catalog_data; assert len(catalog_data.ITEMS) > 100"
    assert_match version.to_s, shell_output("#{bin}/brewcat --version")
  end
end
