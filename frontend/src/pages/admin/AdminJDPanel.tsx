import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Loader2, Trash } from "lucide-react";

export default function AdminJDPanel() {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [jdText, setJdText] = useState("");
  const [loading, setLoading] = useState(false);
  const [jds, setJds] = useState<any[]>([]);
  const [selectedJD, setSelectedJD] = useState<any | null>(null); // ✅ currently opened JD

  const API_BASE = "http://localhost:8000";

  const loadJDs = async () => {
    try {
      const res = await fetch(`${API_BASE}/admin/jds`);
      const data = await res.json();
      setJds(data);
    } catch {
      toast.error("Failed to load JDs");
    }
  };

  const handleAddJD = async () => {
    if (!title || !company || !jdText) {
      toast.error("Please fill in all fields");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/admin/jds`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          company,
          text: jdText, // ✅ correct key matches backend JDCreatePayload
          date: new Date().toISOString(),
        }),
      });

      if (res.ok) {
        toast.success("JD added successfully");
        setTitle("");
        setCompany("");
        setJdText("");
        loadJDs();
      } else {
        toast.error("Failed to add JD");
      }
    } catch {
      toast.error("Failed to connect to server");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteJD = async (id: number) => {
    try {
      await fetch(`${API_BASE}/admin/jds/${id}`, { method: "DELETE" });
      toast.success("JD deleted");
      loadJDs();
    } catch {
      toast.error("Failed to delete JD");
    }
  };

  useEffect(() => {
    loadJDs();
  }, []);

  return (
    <div className="space-y-6">
      {/* JD Creation Form */}
      <Card>
        <CardHeader>
          <CardTitle>Add New Job Description</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            placeholder="Job Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input
            placeholder="Company Name"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
          <Textarea
            placeholder="Enter Job Description..."
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
          />
          <Button onClick={handleAddJD} disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="animate-spin w-4 h-4 mr-2" />
                Adding...
              </>
            ) : (
              "Add JD"
            )}
          </Button>
        </CardContent>
      </Card>

      {/* JD List */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {jds.map((jd) => (
          <Card
            key={jd.id}
            className="relative hover:shadow-md transition-all cursor-pointer"
            onClick={() => setSelectedJD(jd)} // ✅ open modal
          >
            <CardHeader>
              <CardTitle>{jd.title}</CardTitle>
              <p className="text-sm text-muted-foreground">{jd.company}</p>
              <p className="text-xs text-muted-foreground">
                {new Date(jd.date || jd.created_at).toLocaleString()}
              </p>
            </CardHeader>
            <CardContent>
              <p className="text-sm line-clamp-4">{jd.text || jd.jd_text}</p>
              <Button
                variant="destructive"
                size="icon"
                className="absolute top-3 right-3"
                onClick={(e) => {
                  e.stopPropagation(); // prevent opening modal
                  handleDeleteJD(jd.id);
                }}
              >
                <Trash className="w-4 h-4" />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* JD Modal */}
      <Dialog open={!!selectedJD} onOpenChange={() => setSelectedJD(null)}>
        {selectedJD && (
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle className="text-xl font-semibold">
                {selectedJD.title}
              </DialogTitle>
              <DialogDescription>
                <div className="flex items-center justify-between mt-2 text-sm text-muted-foreground">
                  <span>{selectedJD.company}</span>
                  <span>
                    Posted on{" "}
                    {new Date(selectedJD.date || selectedJD.created_at).toLocaleDateString()}
                  </span>
                </div>
              </DialogDescription>
            </DialogHeader>

            <div className="mt-4 max-h-[400px] overflow-y-auto pr-2">
              <p className="whitespace-pre-wrap text-sm leading-relaxed">
                {selectedJD.text || selectedJD.jd_text}
              </p>
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}
