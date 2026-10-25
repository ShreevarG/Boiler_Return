import { useEffect, useMemo, useState } from "react";
import "./index.css";

const API_BASE = "/api";

type Listing = {
  id: string;
  title: string;
  category: string;
  location: string;
  description: string;
  comments: string[];
  demoMode: boolean;
};

type ApiResult<T> = {
  status: string;
  data: T;
  message?: string;
};

async function responseData<T>(response: Response): Promise<T> {
  const result = (await response.json()) as ApiResult<T>;
  if (!response.ok) {
    throw new Error(result.message || "The request could not be completed.");
  }
  return result.data;
}

export default function App() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [listingsError, setListingsError] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [reportOpen, setReportOpen] = useState(false);
  const [reporting, setReporting] = useState(false);
  const [claiming, setClaiming] = useState<Listing | null>(null);
  const [quizQuestion, setQuizQuestion] = useState("");
  const [quizLoading, setQuizLoading] = useState(false);
  const [quizError, setQuizError] = useState("");
  const [claimSubmitting, setClaimSubmitting] = useState(false);
  const [claimResult, setClaimResult] = useState("");
  const [commentText, setCommentText] = useState<Record<string, string>>({});

  useEffect(() => {
    fetch(`${API_BASE}/items`)
      .then(responseData<Listing[]>)
      .then(setListings)
      .catch((error: unknown) => {
        console.error("Could not load listings:", error);
        setListingsError(
          error instanceof Error ? error.message : "Could not load listings.",
        );
      });
  }, []);

  const categories = useMemo(
    () => [...new Set(listings.map((item) => item.category))].sort(),
    [listings],
  );

  const visibleListings = useMemo(
    () =>
      listings.filter((item) => {
        const matchesSearch = `${item.title} ${item.location} ${item.description}`
          .toLowerCase()
          .includes(search.toLowerCase());
        const matchesCategory =
          category === "All" || item.category === category;
        return matchesSearch && matchesCategory;
      }),
    [listings, search, category],
  );

  async function addListing(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setReporting(true);
    const form = event.currentTarget;
    const formData = new FormData(form);

    try {
      const response = await fetch(`${API_BASE}/items`, {
        method: "POST",
        body: formData,
      });
      const newListing = await responseData<Listing>(response);
      setListings((current) => [newListing, ...current]);
      setReportOpen(false);
      form.reset();
    } catch (error) {
      console.error("Could not post the item:", error);
      alert(
        error instanceof Error
          ? error.message
          : "Could not post the item. Check that Flask is running.",
      );
    } finally {
      setReporting(false);
    }
  }

  async function openClaim(item: Listing) {
    setClaiming(item);
    setQuizQuestion("");
    setQuizError("");
    setClaimResult("");
    setQuizLoading(true);
    try {
      const response = await fetch(`${API_BASE}/items/${item.id}/quiz`);
      const quiz = await responseData<{ question: string }>(response);
      setQuizQuestion(quiz.question);
    } catch (error) {
      setQuizError(
        error instanceof Error ? error.message : "Could not load the quiz.",
      );
    } finally {
      setQuizLoading(false);
    }
  }

  async function submitClaim(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!claiming) return;
    setClaimSubmitting(true);
    const formData = new FormData(event.currentTarget);

    try {
      const response = await fetch(
        `${API_BASE}/items/${claiming.id}/claims`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ answer: formData.get("answer") }),
        },
      );
      const result = await responseData<{ passed: boolean; message: string }>(
        response,
      );
      setClaimResult(result.message);
    } catch (error) {
      setClaimResult(
        error instanceof Error ? error.message : "Could not verify your answer.",
      );
    } finally {
      setClaimSubmitting(false);
    }
  }

  async function addComment(
    event: React.FormEvent<HTMLFormElement>,
    itemId: string,
  ) {
    event.preventDefault();
    const comment = commentText[itemId]?.trim();
    if (!comment) return;

    try {
      const response = await fetch(
        `${API_BASE}/items/${itemId}/comments`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ comment }),
        },
      );
      const updatedListing = await responseData<Listing>(response);
      setListings((current) =>
        current.map((item) =>
          item.id === itemId
            ? { ...item, comments: updatedListing.comments }
            : item,
        ),
      );
      setCommentText((current) => ({ ...current, [itemId]: "" }));
    } catch (error) {
      console.error("Could not save the comment:", error);
      alert(
        error instanceof Error ? error.message : "Could not save the comment.",
      );
    }
  }

  return (
    <main>
      <header className="topbar">
        <a className="logo" href="#">BOILER<span> RETURN</span></a>
        <button className="gold-button" onClick={() => setReportOpen(true)}>
          + Report a found item
        </button>
      </header>

      <section className="hero">
        <p className="eyebrow">PURDUE CAMPUS LOST &amp; FOUND</p>
        <h1>Lost something?<br /><span>Let’s bring it back.</span></h1>
        <p>Find what you lost or help a fellow Boilermaker get it back.</p>
        <a className="gold-button link-button" href="#listings">Browse found items ↓</a>
      </section>

      <section className="board" id="listings">
        <div className="section-heading">
          <div>
            <p className="eyebrow dark">THE COMMUNITY BOARD</p>
            <h2>Recently found</h2>
          </div>
          <span>{visibleListings.length} items</span>
        </div>

        <div className="filters">
          <input
            aria-label="Search listings"
            placeholder="Search items or places..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <select
            aria-label="Filter by category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option>All</option>
            {categories.map((itemCategory) => (
              <option key={itemCategory}>{itemCategory}</option>
            ))}
          </select>
        </div>

        {listingsError && <p className="empty">{listingsError}</p>}
        <div className="grid">
          {visibleListings.map((item) => (
            <article className="card" key={item.id}>
              <div className="item-image">📦</div>
              <div className="card-content">
                <span className="tag">{item.category}</span>
                {item.demoMode && <span className="tag">Demo</span>}
                <h3>{item.title}</h3>
                <p className="location">⌖ {item.location}</p>
                <p>{item.description}</p>

                <button className="text-button" onClick={() => openClaim(item)}>
                  Claim this item →
                </button>

                <div className="comments">
                  <strong>Comments</strong>
                  {item.comments.map((comment, index) => (
                    <p className="comment" key={`${item.id}-${index}`}>{comment}</p>
                  ))}
                  <form onSubmit={(event) => addComment(event, item.id)}>
                    <input
                      aria-label={`Comment on ${item.title}`}
                      placeholder="Leave a message for the finder..."
                      value={commentText[item.id] ?? ""}
                      onChange={(event) =>
                        setCommentText((current) => ({
                          ...current,
                          [item.id]: event.target.value,
                        }))
                      }
                    />
                    <button aria-label="Post comment">Post</button>
                  </form>
                </div>
              </div>
            </article>
          ))}
        </div>

        {!listingsError && visibleListings.length === 0 && (
          <p className="empty">No matches. Try a different search.</p>
        )}
      </section>

      <footer>Made for Boilermakers, by Boilermakers.</footer>

      {reportOpen && (
        <div className="overlay" role="presentation">
          <section className="dialog" role="dialog" aria-modal="true">
            <button className="close" onClick={() => setReportOpen(false)}>×</button>
            <p className="eyebrow dark">HELP AN ITEM FIND ITS WAY HOME</p>
            <h2>Report a found item</h2>
            <form className="stack" onSubmit={addListing}>
              <label>Item name<input name="title" required placeholder="e.g. Headphones" /></label>
              <label>Category
                <select name="category" required defaultValue="">
                  <option value="">Choose one</option>
                  <option>Electronics</option>
                  <option>Personal items</option>
                  <option>Clothing</option>
                  <option>Books</option>
                </select>
              </label>
              <label>Where was it found?<input name="location" required placeholder="Building or campus area" /></label>
              <label>Description<textarea name="description" required placeholder="Add a brief general description of the item." /></label>
              <label>Photo (required for verification)<input name="image" type="file" accept="image/*" required /></label>
              <button className="gold-button" disabled={reporting}>
                {reporting ? "Analyzing item..." : "Post listing"}
              </button>
            </form>
          </section>
        </div>
      )}

      {claiming && (
        <div className="overlay" role="presentation">
          <section className="dialog" role="dialog" aria-modal="true">
            <button
              className="close"
              onClick={() => {
                setClaiming(null);
                setClaimResult("");
              }}
            >
              ×
            </button>
            <p className="eyebrow dark">
              {claiming.demoMode ? "DEMO OWNERSHIP QUIZ" : "OWNERSHIP VERIFICATION"}
            </p>
            <h2>Is this your {claiming.title.toLowerCase()}?</h2>
            {quizLoading && <p>Loading the item’s quiz...</p>}
            {quizError && <p role="alert">{quizError}</p>}
            {claimResult && <p role="status">{claimResult}</p>}
            {!quizLoading && !quizError && !claimResult && quizQuestion && (
              <form className="stack" onSubmit={submitClaim}>
                <label>{quizQuestion}
                  <textarea name="answer" required minLength={5} />
                </label>
                <button className="gold-button" disabled={claimSubmitting}>
                  {claimSubmitting ? "Checking answer..." : "Submit answer"}
                </button>
              </form>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
