// Reference runner for Media3's Sonic (tools/sonic_reference/README.md).
// java Run IN.s16 OUT.s16 SPEED IN_RATE OUT_RATE CHANNELS CHUNK_FRAMES
package androidx.media3.common.audio;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.Files;
import java.nio.file.Paths;

public class Run {
  public static void main(String[] a) throws Exception {
    byte[] in = Files.readAllBytes(Paths.get(a[0]));
    float speed = Float.parseFloat(a[2]);
    int inRate = Integer.parseInt(a[3]), outRate = Integer.parseInt(a[4]), ch = Integer.parseInt(a[5]);
    int chunkBytes = Integer.parseInt(a[6]) * ch * 2;
    Sonic s = new Sonic(inRate, ch, speed, 1f, outRate, false);
    ByteBuffer src = ByteBuffer.wrap(in).order(ByteOrder.nativeOrder());
    java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
    while (src.hasRemaining()) {
      int n = Math.min(chunkBytes, src.remaining());
      ByteBuffer part = src.slice().order(ByteOrder.nativeOrder());
      part.limit(n);
      s.queueInput(part);
      src.position(src.position() + n);
      drain(s, out);
    }
    s.queueEndOfStream();
    drain(s, out);
    Files.write(Paths.get(a[1]), out.toByteArray());
  }

  static void drain(Sonic s, java.io.ByteArrayOutputStream out) {
    int size = s.getOutputSize();
    if (size == 0) return;
    ByteBuffer b = ByteBuffer.allocate(size).order(ByteOrder.nativeOrder());
    s.getOutput(b);
    out.write(b.array(), 0, b.position());
  }
}
