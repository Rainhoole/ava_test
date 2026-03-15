'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

export default function Landing() {
  const router = useRouter();
  const [mousePosition, setMousePosition] = useState({ x: 0, y: 0 });
  const [mode, setMode] = useState<'human' | 'agent'>('human');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePosition({
        x: (e.clientX / window.innerWidth - 0.5) * 20,
        y: (e.clientY / window.innerHeight - 0.5) * 20,
      });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-black select-none">
      {/* Corner frames */}
      <div className="absolute top-8 left-8 w-6 h-6 border-l-2 border-t-2 border-white/10" />
      <div className="absolute top-8 right-8 w-6 h-6 border-r-2 border-t-2 border-white/10" />
      <div className="absolute bottom-8 left-8 w-6 h-6 border-l-2 border-b-2 border-white/10" />
      <div className="absolute bottom-8 right-8 w-6 h-6 border-r-2 border-b-2 border-white/10" />

      {/* Subtle grid background */}
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage: `radial-gradient(circle, #fff 1px, transparent 1px)`,
          backgroundSize: '32px 32px',
        }}
      />

      {/* Floating gradient orbs - brand blue tinted */}
      <div
        className="absolute w-[500px] h-[500px] rounded-full blur-[120px] opacity-15"
        style={{
          background: 'radial-gradient(circle, rgba(69,191,255,0.4) 0%, transparent 70%)',
          top: '10%',
          right: '5%',
          transform: `translate(${mousePosition.x * 0.5}px, ${mousePosition.y * 0.5}px)`,
          transition: 'transform 0.3s ease-out',
          animation: 'float 8s ease-in-out infinite',
        }}
      />
      <div
        className="absolute w-[300px] h-[300px] rounded-full blur-[80px] opacity-10"
        style={{
          background: 'radial-gradient(circle, rgba(69,191,255,0.3) 0%, transparent 70%)',
          bottom: '20%',
          left: '10%',
          transform: `translate(${mousePosition.x * -0.3}px, ${mousePosition.y * -0.3}px)`,
          transition: 'transform 0.3s ease-out',
          animation: 'float 10s ease-in-out infinite reverse',
        }}
      />

      {/* Main content */}
      <div className="relative z-10 h-full flex">
        {/* Left section */}
        <div className="flex-1 flex flex-col justify-center px-16 lg:px-24">
          {/* Logo */}
          <div className="flex items-center mb-16">
            <img src="/reforge-logo.png" alt="Reforge" className="h-8" />
          </div>

          {/* Main headline */}
          <h1
            className="text-5xl lg:text-6xl xl:text-7xl font-light tracking-tight leading-[1.1] mb-6 text-white"
            style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
          >
            Research,<br />
            Refined.
          </h1>

          {/* Tagline */}
          <p className="text-lg text-gray-400 mb-12 max-w-md">
            Sharp insights, minimal noise.
          </p>

          {/* Section label */}
          <div className="text-xs tracking-[0.2em] text-gray-600 uppercase mb-8">
            // Agentic Research
          </div>

          {/* Mode tabs */}
          <div className="flex items-center gap-0 mb-6 w-fit border border-white/10 rounded-sm overflow-hidden">
            <button
              onClick={() => setMode('human')}
              className={`px-5 py-2.5 text-xs tracking-[0.1em] uppercase font-medium transition-all duration-200 ${
                mode === 'human'
                  ? 'bg-[#45BFFF] text-black'
                  : 'bg-white/5 text-gray-500 hover:text-gray-300'
              }`}
            >
              I&apos;m a Human
            </button>
            <button
              onClick={() => setMode('agent')}
              className={`px-5 py-2.5 text-xs tracking-[0.1em] uppercase font-medium transition-all duration-200 ${
                mode === 'agent'
                  ? 'bg-[#45BFFF] text-black'
                  : 'bg-white/5 text-gray-500 hover:text-gray-300'
              }`}
            >
              I&apos;m an Agent
            </button>
          </div>

          {/* CTA: Human mode */}
          {mode === 'human' && (
            <button
              onClick={() => router.push('/workspace')}
              className="group inline-flex items-center gap-3 bg-[#45BFFF] text-black px-8 py-4 text-sm tracking-[0.15em] uppercase font-medium hover:bg-[#6DD0FF] transition-all duration-300 w-fit"
            >
              Enter
              <svg
                className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
              </svg>
            </button>
          )}

          {/* CTA: Agent mode */}
          {mode === 'agent' && (
            <div className="relative group w-fit">
              <div className="bg-white/5 text-gray-300 px-6 py-4 font-mono text-sm rounded-sm flex items-center gap-4 border border-white/10">
                <code>curl -s https://research-frontend-sigma.vercel.app/skill.md</code>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText('curl -s https://research-frontend-sigma.vercel.app/skill.md');
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  className="text-gray-500 hover:text-[#45BFFF] transition-colors shrink-0"
                  title="Copy"
                >
                  {copied ? (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right section */}
        <div className="flex-1 flex flex-col justify-between py-16 px-16 lg:px-24">
          {/* Creator info */}
          <div className="self-end text-right">
            <div className="text-[10px] tracking-[0.2em] text-gray-600 uppercase mb-1">
              Created by
            </div>
            <div className="text-sm font-medium tracking-wide text-white">
              REFORGE & FLUXA
            </div>
          </div>

          {/* Floating visual element */}
          <div
            className="relative self-center"
            style={{
              transform: `translate(${mousePosition.x * 0.8}px, ${mousePosition.y * 0.8}px)`,
              transition: 'transform 0.4s ease-out',
            }}
          >
            {/* Abstract visual - dot matrix */}
            <div
              className="relative w-72 h-80 lg:w-80 lg:h-96"
              style={{ animation: 'float 6s ease-in-out infinite' }}
            >
              {/* Card background */}
              <div className="absolute inset-0 bg-white/[0.03] rounded-2xl border border-white/10 backdrop-blur-sm" />

              {/* Card content */}
              <div className="relative h-full p-6 flex flex-col">
                {/* Card header */}
                <div className="flex items-center justify-between mb-4">
                  <img src="/reforge-logo.png" alt="Reforge" className="h-4" />
                  <div className="text-[10px] tracking-[0.15em] text-gray-600 uppercase">
                    // AVA
                  </div>
                </div>

                {/* Wave dot art - brand blue tinted */}
                <div className="flex-1 flex items-center justify-center overflow-hidden">
                  <div className="relative w-full h-full">
                    <svg viewBox="0 0 100 120" className="w-full h-full">
                      {/* Wave 1 - Top, lightest */}
                      <circle cx="5" cy="35" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="12" cy="32" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="19" cy="30" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="26" cy="29" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="33" cy="30" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="40" cy="33" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="47" cy="37" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="54" cy="40" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="61" cy="42" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="68" cy="43" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="75" cy="42" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="82" cy="39" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="89" cy="35" r="1.5" fill="#45BFFF" opacity="0.2" />
                      <circle cx="96" cy="30" r="1.5" fill="#45BFFF" opacity="0.2" />

                      {/* Wave 2 */}
                      <circle cx="5" cy="50" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="12" cy="46" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="19" cy="43" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="26" cy="42" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="33" cy="43" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="40" cy="47" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="47" cy="52" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="54" cy="56" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="61" cy="58" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="68" cy="58" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="75" cy="56" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="82" cy="52" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="89" cy="46" r="2" fill="#45BFFF" opacity="0.3" />
                      <circle cx="96" cy="40" r="2" fill="#45BFFF" opacity="0.3" />

                      {/* Wave 3 - Middle */}
                      <circle cx="5" cy="68" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="12" cy="63" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="19" cy="59" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="26" cy="57" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="33" cy="58" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="40" cy="62" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="47" cy="68" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="54" cy="73" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="61" cy="76" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="68" cy="76" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="75" cy="73" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="82" cy="68" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="89" cy="61" r="2.5" fill="#45BFFF" opacity="0.4" />
                      <circle cx="96" cy="54" r="2.5" fill="#45BFFF" opacity="0.4" />

                      {/* Wave 4 */}
                      <circle cx="5" cy="88" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="12" cy="82" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="19" cy="77" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="26" cy="74" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="33" cy="75" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="40" cy="80" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="47" cy="87" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="54" cy="93" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="61" cy="96" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="68" cy="96" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="75" cy="93" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="82" cy="87" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="89" cy="79" r="3" fill="#45BFFF" opacity="0.55" />
                      <circle cx="96" cy="70" r="3" fill="#45BFFF" opacity="0.55" />

                      {/* Wave 5 - Bottom, brightest */}
                      <circle cx="5" cy="110" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="12" cy="103" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="19" cy="97" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="26" cy="93" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="33" cy="94" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="40" cy="99" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="47" cy="107" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="54" cy="113" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="61" cy="116" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="68" cy="116" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="75" cy="112" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="82" cy="105" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="89" cy="96" r="3.5" fill="#45BFFF" opacity="0.75" />
                      <circle cx="96" cy="86" r="3.5" fill="#45BFFF" opacity="0.75" />
                    </svg>
                  </div>
                </div>

                {/* Card footer */}
                <div className="pt-4 border-t border-white/10">
                  <div className="text-xs text-gray-600 tracking-wide">
                    agent.001
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom spacer */}
          <div />
        </div>
      </div>

      {/* Floating animation keyframes are in globals.css */}
    </main>
  );
}
