class Brewcat < Formula
  desc "Visual catalog of Homebrew packages, skills and MCP servers for devs and gamers"
  homepage "https://github.com/1985epma/homebrew-brewcat"
  url "https://github.com/1985epma/homebrew-brewcat/archive/refs/tags/v0.1.2.2.tar.gz"
  sha256 "4d8b3e2f9ca12e66f94014214e93fcb5c7268348addfae0c3f15f2b3e1a2228b"
  license "MIT"

  depends_on "python-tk"

  def install
    libexec.install "app.py", "catalog_data.py", "extras_tab.py", "logo.py", "help_text.py"
    libexec.install "assets"
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
  end
end
