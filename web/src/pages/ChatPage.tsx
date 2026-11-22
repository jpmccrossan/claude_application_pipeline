import Chat from "../components/Chat";

export default function ChatPage() {
  return (
    <>
      <div className="page-head">
        <div><div className="kicker">Assistant</div><h1>Chat with Claude</h1></div>
        <span className="muted small" style={{ maxWidth: 420 }}>
          For one application, open it from Applications: its chat edits that CV and letter directly.
        </span>
      </div>
      <Chat full title="General chat" hints={[
        "Add my new certification to my facts",
        "Make my letters sound a bit more formal from now on",
        "What open TODO questions are in my facts?",
        "Shorten the default bullets in my profile",
      ]} />
    </>
  );
}
