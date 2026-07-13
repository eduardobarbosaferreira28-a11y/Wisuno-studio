/**
 * transcode.js — browser-side crop + downscale before upload.
 *
 * The uplink, not the server, is the bottleneck for Video Studio: a 4K source is
 * ~2 GB and takes ~25 minutes to upload, and the server's very first step throws
 * those pixels away by cropping to a centred 9:16 window and scaling to 1080×1920.
 * So we do that crop in the browser and upload ~150 MB instead of ~2 GB.
 *
 * There is a second, larger win hiding in this: video_service._run_analysis skips
 * its full-4K ffmpeg re-encode entirely when the upload is ALREADY exactly
 * 1080×1920 ("already portrait — skipping crop"). That check is a strict equality,
 * so OUT_W/OUT_H below must match PORTRAIT_OUT_W/PORTRAIT_OUT_H on the server.
 *
 * Constraints that are load-bearing — do not "simplify" these away:
 *   - Output MUST be .mp4/H.264. The backend's ALLOWED_EXTS rejects .webm.
 *   - Audio MUST survive. ElevenLabs Scribe transcribes this file; no audio means
 *     no transcript, which means no cut analysis.
 *   - Frame rate MUST stay constant and identical to the source. The render
 *     frame-locks karaoke captions to the file's r_frame_rate; a variable or
 *     resampled rate makes captions drift behind the speaker (the bug fixed in
 *     82f26c7 / d0ef016). We therefore never pass `frameRate` to the conversion,
 *     and we never use MediaRecorder/captureStream, which emit VFR.
 *
 * Anything unexpected → return the original file and let the server do the work.
 * This is an optimisation; it must never be the reason an upload fails.
 */
(function () {
  'use strict';

  // Must equal PORTRAIT_OUT_W / PORTRAIT_OUT_H in studio/backend/services/video_service.py
  const OUT_W = 1080;
  const OUT_H = 1920;

  const VIDEO_BITRATE = 4_000_000;  // ~4 Mbps — sets upload time; pipeline re-encodes at CRF 22 anyway
  const AUDIO_BITRATE = 128_000;    // matches the server's `-c:a aac -b:a 128k`

  // Vendored ESM bundle, lazily imported so it only costs bandwidth when we actually
  // transcode. Deliberately named .js, not .mjs: the backend serves /js via Starlette's
  // StaticFiles, which types files from Python's mimetypes, and a module import is
  // rejected outright on a non-JS MIME type. `.js` is guaranteed correct everywhere.
  let _mb = null;
  async function lib() {
    if (!_mb) _mb = await import('/js/mediabunny.esm.js');
    return _mb;
  }

  function mp4Name(name) {
    return `${(name || 'video').replace(/\.[^.]+$/, '')}.mp4`;
  }

  /**
   * Crop + downscale `file` to exactly 1080×1920 H.264/AAC MP4.
   * Returns the ORIGINAL file untouched if a transcode isn't needed or isn't possible.
   *
   * @param {File} file
   * @param {(pct:number)=>void} [onProgress] 0..100
   * @returns {Promise<File>}
   */
  async function prepare(file, onProgress) {
    const report = (pct) => { try { onProgress && onProgress(pct); } catch (_) {} };

    let conversion = null;
    try {
      const {
        Input, Output, Conversion, BlobSource, BufferTarget, Mp4OutputFormat,
        ALL_FORMATS, canEncodeVideo,
      } = await lib();

      if (typeof VideoEncoder === 'undefined' || !(await canEncodeVideo('avc'))) {
        console.warn('[transcode] WebCodecs H.264 encoding unavailable — uploading original.');
        return file;
      }

      const input = new Input({ source: new BlobSource(file), formats: ALL_FORMATS });
      const track = await input.getPrimaryVideoTrack();
      if (!track) {
        console.warn('[transcode] no video track found — uploading original.');
        return file;
      }

      // Already the exact size the server wants: uploading it as-is also makes the
      // server skip its crop, so there is nothing to gain from re-encoding.
      if (track.displayWidth === OUT_W && track.displayHeight === OUT_H) {
        console.info('[transcode] source is already 1080×1920 — uploading as-is.');
        return file;
      }

      const output = new Output({ format: new Mp4OutputFormat(), target: new BufferTarget() });

      conversion = await Conversion.init({
        input,
        output,
        // `cover` scales to fill 1080×1920 and centre-crops the overflow — the same
        // largest-centred-9:16-window the server's _compute_portrait_crop() takes.
        // No `frameRate` here, deliberately: the source rate must pass through intact.
        video: { width: OUT_W, height: OUT_H, fit: 'cover', codec: 'avc', bitrate: VIDEO_BITRATE },
        audio: { codec: 'aac', bitrate: AUDIO_BITRATE },
      });

      if (!conversion.isValid) {
        console.warn('[transcode] conversion rejected the input — uploading original.',
          conversion.discardedTracks);
        return file;
      }

      // Losing the audio track would silently break transcription downstream, and the
      // failure would only surface as "no cuts proposed" much later. Bail out instead.
      const audioDiscarded = (conversion.discardedTracks || [])
        .some((d) => d && d.track && d.track.type === 'audio');
      if (audioDiscarded) {
        console.warn('[transcode] audio track would be dropped — uploading original.');
        return file;
      }

      conversion.onProgress = (p) => report(Math.round((p || 0) * 100));
      await conversion.execute();

      const buf = output.target.buffer;
      if (!buf || !buf.byteLength) {
        console.warn('[transcode] produced an empty file — uploading original.');
        return file;
      }

      const out = new File([buf], mp4Name(file.name), { type: 'video/mp4' });
      console.info(
        `[transcode] ${track.displayWidth}×${track.displayHeight} → ${OUT_W}×${OUT_H} · ` +
        `${(file.size / 1048576).toFixed(0)} MB → ${(out.size / 1048576).toFixed(0)} MB`
      );

      // A transcode that grew the file (already-small or already-portrait sources) is
      // strictly worse for the thing we are optimising. Send the smaller one.
      return out.size < file.size ? out : file;
    } catch (err) {
      console.warn('[transcode] failed — uploading original.', err);
      return file;
    } finally {
      report(100);
    }
  }

  window.videoTranscoder = { prepare, OUT_W, OUT_H };
})();
