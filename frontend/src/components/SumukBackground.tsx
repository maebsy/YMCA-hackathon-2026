"use client";

import React, { useEffect, useRef } from "react";

interface AquaRipple {
  x: number;
  y: number;
  r: number;
  maxR: number;
  alpha: number;
  isMint: boolean;
}

export const SumukBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let cw = (canvas.width = window.innerWidth);
    let ch = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      cw = canvas.width = window.innerWidth;
      ch = canvas.height = window.innerHeight;
    };

    window.addEventListener("resize", handleResize, { passive: true });

    const ripples: AquaRipple[] = [];
    let animId: number | null = null;
    let lastSpawnTime = 0;

    const renderRippleLoop = () => {
      ctx.clearRect(0, 0, cw, ch);

      for (let i = ripples.length - 1; i >= 0; i--) {
        const d = ripples[i];
        d.r += (d.maxR - d.r) * 0.07;
        d.alpha *= 0.96;

        if (d.alpha < 0.004) {
          ripples.splice(i, 1);
          continue;
        }

        ctx.save();
        const grad = ctx.createRadialGradient(
          d.x,
          d.y,
          d.r * 0.1,
          d.x,
          d.y,
          d.r
        );
        if (d.isMint) {
          grad.addColorStop(0, `rgba(45, 212, 191, ${d.alpha})`);
          grad.addColorStop(0.65, `rgba(56, 189, 248, ${d.alpha * 0.45})`);
          grad.addColorStop(1, "rgba(45, 212, 191, 0)");
        } else {
          grad.addColorStop(0, `rgba(56, 189, 248, ${d.alpha})`);
          grad.addColorStop(0.7, `rgba(45, 212, 191, ${d.alpha * 0.4})`);
          grad.addColorStop(1, "rgba(56, 189, 248, 0)");
        }

        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.restore();
      }

      if (ripples.length > 0) {
        animId = requestAnimationFrame(renderRippleLoop);
      } else {
        animId = null;
      }
    };

    const spawnRipple = (x: number, y: number, isClick = false) => {
      if (ripples.length > 24) ripples.shift();
      ripples.push({
        x,
        y,
        r: isClick ? 14 : 6,
        maxR: isClick ? 130 + Math.random() * 40 : 48 + Math.random() * 24,
        alpha: isClick ? 0.18 : 0.08,
        isMint: Math.random() > 0.5,
      });

      if (!animId) {
        animId = requestAnimationFrame(renderRippleLoop);
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      const now = performance.now();
      if (now - lastSpawnTime > 65) {
        spawnRipple(e.clientX, e.clientY, false);
        lastSpawnTime = now;
      }
    };

    const handleClick = (e: MouseEvent) => {
      spawnRipple(e.clientX, e.clientY, true);
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    window.addEventListener("click", handleClick, { passive: true });

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("click", handleClick);
      if (animId) cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <>
      {/* 재사용 가능한 스마트 물결(Aqua Drop) SVG 심볼 */}
      <svg
        width="0"
        height="0"
        style={{ position: "absolute", pointerEvents: "none" }}
        aria-hidden="true"
      >
        <defs>
          <g id="ink-bleed-motif">
            <circle cx="100" cy="100" r="88" fill="currentColor" opacity="0.12" />
            <circle cx="100" cy="100" r="62" fill="currentColor" opacity="0.18" />
            <circle cx="100" cy="100" r="36" fill="currentColor" opacity="0.26" />
          </g>
          <path
            id="brush-stroke-path"
            d="M2,12 C75,4 195,4 298,12 C225,16 95,16 2,12 Z"
            fill="currentColor"
          />
        </defs>
      </svg>

      {/* 스마트 화이트 × 라이트블루 × 라이트민트 배경 */}
      <div className="smart-aqua-bg">
        <div className="smart-grid-overlay" />
        <canvas
          id="sumuk-canvas"
          ref={canvasRef}
          className="absolute inset-0 w-full h-full"
        />
      </div>
    </>
  );
};
