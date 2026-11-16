"""程序化生成 34s 轻量圣诞氛围 BGM（铃铛 + 低音铺底 + 轻柔打击），无版权风险。"""
import numpy as np, wave
SR=44100; DUR=34.0
n=int(SR*DUR); t=np.arange(n)/SR
rng=np.random.default_rng(7)

def env(a,d,s,r,gate):
    out=np.zeros(n)
    i=0
    while i<len(gate):
        j=min(len(gate),i+gate[i]); out[i:j]=1; i=j
    return out*gate

# --- 低音铺底：C - Am - F - G 循环，正弦 + 微失谐
chords=[(130.81,196.00,261.63),(110.00,164.81,220.00),(87.31,174.61,261.63),(98.00,130.81,196.00)]
pad=np.zeros(n)
bar=4.0
for b in range(int(np.ceil(DUR/bar))):
    f=chords[b%4]
    i0=int(b*bar*SR); i1=min(n,int((b+1)*bar*SR))
    tt=t[i0:i1]-t[i0]
    seg=np.zeros(i1-i0)
    for k,fr in enumerate(f):
        v=(0.55/(k+1))*np.sin(2*np.pi*fr*tt)+0.25*np.sin(2*np.pi*fr*1.003*tt)
        seg+=v
    fade=np.minimum(1,tt/0.6)*np.minimum(1,(bar-tt)/0.8)
    pad[i0:i1]+=seg*fade*0.20

# --- 铃铛（celesta 般的泛音衰减）
notes=[1046.5,1318.5,1568.0,1318.5,1174.7,1568.0,1760.0,1318.5]
bell=np.zeros(n)
step=0.5
for k in range(int(DUR/step)):
    fr=notes[k%len(notes)]
    i0=int(k*step*SR); L=int(1.6*SR); i1=min(n,i0+L)
    if i1<=i0: break
    tt=np.arange(i1-i0)/SR
    seg=(np.sin(2*np.pi*fr*tt)*0.6+np.sin(2*np.pi*fr*2*tt)*0.25+np.sin(2*np.pi*fr*3.01*tt)*0.12)
    e=np.exp(-tt*3.2)*(1-np.exp(-tt*400))
    bell[i0:i1]+=seg*e*0.11

# --- 轻柔底鼓 & 沙锤
kick=np.zeros(n); hat=np.zeros(n)
for k in range(int(DUR/0.5)):
    i0=int(k*0.5*SR); L=int(0.25*SR); i1=min(n,i0+L)
    tt=np.arange(i1-i0)/SR
    if k%2==0:
        kick[i0:i1]+=np.sin(2*np.pi*(60+40*np.exp(-tt*30))*tt)*np.exp(-tt*12)*0.22
    h=rng.standard_normal(i1-i0)*np.exp(-tt*55)*0.05
    hat[i0:i1]+=h

mix=pad+bell+kick+hat
# 简易混响（指数衰减卷积）
ir_len=int(0.9*SR); ir=rng.standard_normal(ir_len)*np.exp(-np.arange(ir_len)/(0.25*SR))
ir/=np.abs(ir).sum()**0.5
wet=np.convolve(mix,ir,mode="same")*0.35
out=mix+wet
# 首尾淡入淡出
f_out=0.4
fi=int(0.15*SR); fo=int(2.2*SR)
out[:fi]*=np.linspace(0,1,fi); out[-fo:]*=np.linspace(1,0,fo)
out/=max(1e-9,np.abs(out).max())
out*=0.62
pcm=(out*32767).astype(np.int16)
st=np.stack([pcm,pcm],axis=1)
with wave.open("05_edit/bgm.wav","wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(st.tobytes())
print("bgm ok", DUR)
