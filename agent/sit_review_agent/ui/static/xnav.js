// The review document's one script: the exported page inlines it (ui/export.py NAV_JS) and dra ui loads this same
// file for a run's Review tab (app.js), so the two cannot drift apart. It hides and shows the sections already in the
// page, opens a link's target in the side pane without moving the main column, previews a link's target on hover,
// marks the section in view in the table of contents, and moves to a target with a way back. Without script every
// section shows and every link is a plain anchor.
//
// sitXnav(box, opt) wires one review document inside `box`. opt.history (default true, the exported page): the pane's
// steps, "Show in the report" and the sidebar's parts are browser history entries, so Back returns to the place the
// reader left. With opt.history false (the app, whose own router owns history) the pane keeps its own stack, nothing
// is pushed and every in-document link is handled here. opt.top() is the height of the page's fixed chrome above the
// document; opt.more(id) may return { href, label } for one more action in the pane; opt.column (default ".wrap") is
// the reading column that makes room for the pane. The returned object's destroy()
// removes every listener; they also remove themselves once `box` has left the page.
(function () {
  function xnav(box, opt) {
    opt = opt || {};
    var hist = opt.history !== false;
    var root = document.documentElement; root.classList.add("js");
    var secs = box.querySelectorAll(".sec"), items = box.querySelectorAll(".toc-item");
    var heads = box.querySelectorAll(".toc-heads a"), back = box.querySelector(".x-back"), cur = "all";
    var toc = box.querySelector(".toc"), marks = [], offs = [];
    function on(t, type, fn, o) {
      var g = function (e) { if (!box.isConnected) { destroy(); return; } fn(e); };
      t.addEventListener(type, g, o);
      offs.push([t, type, g, o]);
    }
    function destroy() {
      for (var i = 0; i < offs.length; i++) offs[i][0].removeEventListener(offs[i][1], offs[i][2], offs[i][3]);
      offs = [];
      root.classList.remove("pane-open");
    }
    function chrome() { return opt.top ? opt.top() : 0; }
    if (hist) { try { history.scrollRestoration = "manual"; } catch (x) {} }
    function st() { var s = hist ? history.state : null; return s && typeof s === "object" ? s : {}; }
    function put(s, url) { if (!hist) return; try { history.replaceState(s, "", url === undefined ? location.href : url); } catch (x) {} }
    function save() { if (!hist) return; var s = {}, o = st(); for (var k in o) s[k] = o[k]; s.y = window.scrollY; s.g = cur; put(s); }
    function show(g, top) {
      cur = g;
      for (var i = 0; i < secs.length; i++) secs[i].hidden = g !== "all" && secs[i].getAttribute("data-g") !== g;
      for (var j = 0; j < items.length; j++) items[j].classList.toggle("active", items[j].getAttribute("data-g") === g);
      if (top) window.scrollTo(0, 0);
      spy();
    }
    function hit(t) {
      var old = box.querySelectorAll(".x-hit");
      for (var i = 0; i < old.length; i++) old[i].classList.remove("x-hit");
      var b = t.closest("article, li, tr, .x-entry, mark, .doc-page") || t;
      if (t.classList.contains("doc-sec") || t.classList.contains("doc-page")) b = t;
      b.classList.add("x-hit");
    }
    function go(t) {
      var sec = t.closest(".sec"), g = sec && sec.getAttribute("data-g");
      if (g && (sec.hidden || (cur !== "all" && cur !== g))) show(g, false);
      var y = window.scrollY + t.getBoundingClientRect().top - (window.innerHeight - chrome()) / 3 - chrome();
      if (t.tagName === "MARK") window.scrollTo(0, y);
      else t.scrollIntoView({ block: "start" });
      hit(t);
    }
    function backVis() { if (back) back.hidden = !(hist ? st().depth > 0 : marks.length > 0); }
    function route() {
      var h = location.hash, m = /^#g(\d)$/.exec(h), s = st();
      var t = h.length > 1 && !m ? document.getElementById(decodeURIComponent(h.slice(1))) : null;
      if (m) show(m[1], typeof s.y !== "number");
      else if (typeof s.g === "string") show(s.g, false);
      else if (!t) show("all", false);
      if (typeof s.y === "number") { window.scrollTo(0, s.y); if (t) hit(t); }
      else if (t) go(t);
      backVis();
    }
    function landing() {                                 // the app: a link opened in its own tab lands on its target
      var h = location.hash, t = h.length > 1 ? document.getElementById(decodeURIComponent(h.slice(1))) : null;
      if (t && box.contains(t)) go(t);
      spy();
    }
    function target(a) {
      var id = decodeURIComponent(a.getAttribute("href").slice(1)), t = id && document.getElementById(id);
      return t && box.contains(t) ? t : null;
    }
    if (toc) on(toc, "click", function (e) {
      var a = e.target.closest("a[data-g]");
      if (!a) return;
      var g = a.getAttribute("data-g");
      if (!hist) {                                       // every section shows: a part or a heading is a place to go
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        var t = target(a);
        if (t) t.scrollIntoView({ block: "start" });
        return;
      }
      if (!a.classList.contains("toc-item")) { save(); show(g, false); return; }
      e.preventDefault();
      show(g, true);
      put(st(), g === "all" ? location.pathname + location.search : "#g" + g);
    });
    // a cross-link opens its target in the side pane and the main column does not move; a modified click, a wheel-button
    // click, the sidebar and the header's own links keep their plain anchor behaviour
    on(document, "click", function (e) {
      if (e.button !== 0) return;
      var a = e.target.closest ? e.target.closest("a[href^='#']") : null;
      if (a && a.classList.contains("x-back") && box.contains(a)) {
        e.preventDefault();
        if (hist) history.back();
        else if (marks.length) { window.scrollTo(0, marks.pop()); backVis(); }
        return;
      }
      if (!a) {
        // a target its own handler has just replaced (the pane's breadcrumb redraws itself) was inside the pane
        if (paneOpen() && e.target.isConnected && !(e.target.closest && e.target.closest(".x-pane, .x-pop, .toc")))
          closePane();
        return;
      }
      if (a.closest(".toc") || a.closest(".exp-head") || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var t = target(a);
      if (!t) {
        if (!hist && box.contains(a)) e.preventDefault();   // the app's router never sees an in-document hash
        return;
      }
      e.preventDefault();
      openPane(t.id, a);
    });
    function jump(id) {                                  // move the main column to a target, with a way back
      var t = document.getElementById(id);
      if (!t) return;
      if (!hist) {
        marks.push(window.scrollY);
        try { history.replaceState(history.state, "", "#" + id); } catch (x) {}
        go(t);
        backVis();
        return;
      }
      var d = st().depth || 0;
      save();
      try { history.pushState({ depth: d + 1 }, "", "#" + id); } catch (x) {}
      go(t);
      backVis();
    }
    if (hist) {
      on(window, "popstate", function (e) {
        var s = e.state;
        if (s && typeof s.pane === "number" && s.stack) { adopt(s); return; }
        if (paneOpen()) {                                // Back past the pane's first entry: close it, main stays put
          closed();
          if (after) { var f = after; after = null; f(); }
          return;
        }
        route();
      });
      on(window, "hashchange", function () { if (!paneOpen()) route(); });
    }
    // the section in view, marked in the table of contents
    var ticking = false;
    function spy() {
      var best = null, line = chrome() + 96;
      for (var i = 0; i < secs.length; i++) {
        if (secs[i].hidden) continue;
        if (secs[i].getBoundingClientRect().top <= line) best = secs[i]; else if (best) break;
      }
      if (!best) for (var k = 0; k < secs.length; k++) if (!secs[k].hidden) { best = secs[k]; break; }
      var on_ = null;
      for (var j = 0; j < heads.length; j++) {
        var is = !!best && heads[j].getAttribute("href") === "#" + best.id;
        heads[j].classList.toggle("cur", is);
        if (is) on_ = heads[j];
      }
      var part = null;
      if (!hist) {                                       // the app: the part in view, too
        for (var p = 0; p < items.length; p++) {
          var here = !!best && items[p].getAttribute("data-g") === best.getAttribute("data-g");
          items[p].classList.toggle("cur", here);
          if (here) { part = items[p]; items[p].setAttribute("aria-current", "location"); }
          else items[p].removeAttribute("aria-current");
        }
      }
      var box2 = box.querySelector(".toc-inner");       // keep the marked heading in the rail's view
      if (on_ && box2 && box2.scrollHeight > box2.clientHeight && on_.offsetParent &&
          (on_.offsetTop < box2.scrollTop + 48 || on_.offsetTop > box2.scrollTop + box2.clientHeight - 48))
        box2.scrollTop = on_.offsetTop - box2.clientHeight / 2;
      if (part && box2 && box2.scrollWidth > box2.clientWidth &&      // a one-line strip: the part in its view, clear
          (part.offsetLeft < box2.scrollLeft + 72 ||                     // of the faded edges
           part.offsetLeft + part.offsetWidth > box2.scrollLeft + box2.clientWidth - 72))
        box2.scrollLeft = part.offsetLeft - 72;
      edges();
    }
    // a one-line strip of parts (the app below 1280 px): an edge that has more beyond it fades, so no label ends
    // in a hard cut, and a mouse wheel over the strip scrolls it sideways
    var bar = box.querySelector(".toc-inner");
    function edges() {
      if (!bar || hist) return;
      var wide = bar.scrollWidth > bar.clientWidth + 1;
      bar.classList.toggle("x-fade-l", wide && bar.scrollLeft > 1);
      bar.classList.toggle("x-fade-r", wide && bar.scrollLeft + bar.clientWidth < bar.scrollWidth - 1);
    }
    if (bar && !hist) {
      on(bar, "scroll", edges, { passive: true });
      on(window, "resize", edges);
      on(bar, "wheel", function (e) {
        if (bar.scrollWidth <= bar.clientWidth + 1 || Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
        e.preventDefault();
        bar.scrollLeft += e.deltaY;
      }, { passive: false });
    }
    on(window, "scroll", function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(function () { ticking = false; spy(); }); }
    }, { passive: true });
    // the preview of a link's target, on hover or keyboard focus
    var pop = document.createElement("div"), timer = 0, shown = null;
    pop.className = "x-pop"; pop.hidden = true; pop.setAttribute("role", "tooltip");
    box.appendChild(pop);
    function strip(n) {
      var all = n.querySelectorAll("[id]");
      for (var i = 0; i < all.length; i++) all[i].removeAttribute("id");
      if (n.removeAttribute) n.removeAttribute("id");
      return n;
    }
    function el(tag, cls, text) {
      var n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text) n.textContent = text;
      return n;
    }
    function pdfOf(t) {
      var p = t.closest(".doc-page"), l = p && p.querySelector(".x-pdf");
      return l ? strip(l.cloneNode(true)) : null;
    }
    function preview(t) {
      var box = el("div", "x-pop-in"), page = t.closest(".doc-page");
      if (page) {
        box.appendChild(el("div", "x-pop-kicker", page.getAttribute("data-label")));
        var pre = t.closest("pre") || page.querySelector("pre"), r = document.createRange(), q = el("div", "x-pop-doc");
        if (t.tagName === "MARK" || t.classList.contains("doc-sec")) {
          r.setStart(pre, 0); r.setEndBefore(t); var before = r.toString();
          r.setStartAfter(t); r.setEnd(pre, pre.childNodes.length); var after = r.toString();
          q.appendChild(document.createTextNode(before));               // the whole page, scrolled to the quote
          if (t.tagName === "MARK") q.appendChild(el("mark", "", t.textContent));
          else q.appendChild(el("b", "", t.getAttribute("data-label") + "\n"));
          q.appendChild(document.createTextNode(after));
        } else {
          q.textContent = pre.textContent;
        }
        box.appendChild(q);
        var pdf = pdfOf(t); if (pdf) box.appendChild(pdf);
      } else if (t.tagName === "ARTICLE") {
        var h = t.querySelector("h3"), meta = t.querySelector(".x-meta"), p = t.querySelector(":scope > p");
        if (h) box.appendChild(strip(el("div", "x-pop-title", h.textContent)));
        if (meta) box.appendChild(strip(meta.cloneNode(true)));
        if (p) box.appendChild(strip(p.cloneNode(true)));
      } else if (t.tagName === "TR") {
        var cells = t.querySelectorAll("td"), dl = el("div", "x-pop-row"), hs = t.closest("table").querySelectorAll("th");
        for (var i = 0; i < cells.length; i++) {
          var line = el("div");
          line.appendChild(el("span", "x-pop-k", (hs[i] ? hs[i].textContent : "") + " "));
          line.appendChild(strip(cells[i].cloneNode(true)));
          dl.appendChild(line);
        }
        box.appendChild(dl);
      } else {
        box.appendChild(strip(t.cloneNode(true)));
      }
      return box;
    }
    function hide() { clearTimeout(timer); pop.hidden = true; shown = null; }
    function place(a) {
      var row = a.classList.contains("x-rowlink") ? a.closest("tr") : null;   // a whole-row link: clear of its row
      var r = (row || a).getBoundingClientRect(), w = Math.min(460, window.innerWidth - 32), vh = window.innerHeight;
      pop.style.width = w + "px";
      pop.style.left = Math.max(16, Math.min(r.left, window.innerWidth - w - 16)) + "px";
      pop.style.maxHeight = "";
      pop.hidden = false;
      var h = pop.offsetHeight, below = r.bottom + 4, above = r.top - 4;
      if (below + h <= vh - 8) pop.style.top = below + "px";           // under the link, 4 px from it
      else if (above - h >= 8) pop.style.top = (above - h) + "px";      // flipped above it
      else if (vh - 8 - below >= above - 8) {
        pop.style.top = below + "px"; pop.style.maxHeight = (vh - 8 - below) + "px";
      }
      else { pop.style.top = "8px"; pop.style.maxHeight = (above - 8) + "px"; }
      var m = pop.querySelector(".x-pop-doc mark, .x-pop-doc b");      // a passage: its quote in view
      if (m) pop.scrollTop = Math.max(0, m.offsetTop - 96);
    }
    function arm(a) {
      if (a === shown) return;
      clearTimeout(timer);
      timer = setTimeout(function () {
        var t = target(a);
        if (!t) return;
        pop.textContent = ""; pop.appendChild(preview(t)); shown = a; place(a);
      }, 220);
    }
    var canHover = !window.matchMedia || window.matchMedia("(hover: hover)").matches;
    function inPop(e) { return !!(e.target.closest && e.target.closest(".x-pop")); }
    function link(e) {
      var a = e.target.closest ? e.target.closest("a.xref, a.chip") : null;
      return a && !a.closest(".x-pop") && a.getAttribute("href").charAt(0) === "#" ? a : null;
    }
    if (canHover) {
      on(document, "mouseover", function (e) {
        var a = link(e);
        if (a) arm(a);
        else if (inPop(e)) clearTimeout(timer);                        // on the card: it stays open
        else { clearTimeout(timer); if (shown && !pop.contains(document.activeElement)) timer = setTimeout(hide, 250); }
      });
    }
    on(document, "focusin", function (e) {
      var a = link(e);
      if (a) arm(a); else if (!inPop(e)) hide();
    });
    on(document, "keydown", function (e) {
      if (e.key !== "Escape") return;
      if (!pop.hidden) { hide(); return; }
      if (paneOpen()) { e.preventDefault(); closePane(); }
    });
    // ---- the side pane: the target's own content, copied from the page with its ids stripped
    var pane = box.querySelector(".x-pane"), pbody = null, ptitle = null, pkick = null, pcrumb = null;
    var pprev = null, pnext = null, pshow = null, ppdf = null, pmore = null, stack = [], at = -1, depth = 0, opener = null;
    var after = null, gen = 0;
    function step(i) { if (i >= 0 && i < stack.length && i !== at) { at = i; draw(); } }
    if (pane) {
      pbody = pane.querySelector(".x-pane-body"); ptitle = pane.querySelector(".x-pane-title");
      pkick = pane.querySelector(".x-pane-kicker"); pcrumb = pane.querySelector(".x-pane-crumb");
      pprev = pane.querySelector(".x-pane-prev"); pnext = pane.querySelector(".x-pane-next");
      pshow = pane.querySelector(".x-pane-show"); ppdf = pane.querySelector(".x-pane-pdf");
      if (opt.more) {
        pmore = el("a", "x-pane-more"); pmore.hidden = true;
        pane.querySelector(".x-pane-actions").appendChild(pmore);
      }
      pprev.addEventListener("click", function () { if (hist) history.back(); else step(at - 1); });
      pnext.addEventListener("click", function () { if (hist) history.forward(); else step(at + 1); });
      pane.querySelector(".x-pane-close").addEventListener("click", function () { closePane(); });
      pshow.addEventListener("click", function () {
        var id = stack[at];
        after = function () { jump(id); };
        closePane();
      });
      pcrumb.addEventListener("click", function (e) {
        var b = e.target.closest("button[data-i]");
        if (!b) return;
        var i = +b.getAttribute("data-i");
        if (i === at) return;
        if (hist) history.go(i - at); else step(i);
      });
    }
    function paneOpen() { return !!pane && !pane.hidden; }
    function block(t) {
      return t.closest(".doc-page") || t.closest("article.finding, .x-entry, li, tr") || t;
    }
    function copy(t, b) {
      t.setAttribute("data-x-here", "");
      var c;
      if (b.tagName === "TR") {
        var table = b.closest("table"), head = table.querySelector("thead");
        var tb = document.createElement("table"), body = document.createElement("tbody");
        if (head) tb.appendChild(head.cloneNode(true));
        body.appendChild(b.cloneNode(true)); tb.appendChild(body);
        c = el("div", "x-table"); c.appendChild(tb);
      } else {
        c = b.cloneNode(true);
      }
      t.removeAttribute("data-x-here");
      var stale = c.querySelectorAll(".x-hit, .x-opener");
      for (var i = 0; i < stale.length; i++) stale[i].classList.remove("x-hit", "x-opener");
      var here = c.querySelector("[data-x-here]") || (c.hasAttribute && c.hasAttribute("data-x-here") ? c : null);
      if (here) { here.removeAttribute("data-x-here"); if (here !== c) here.classList.add("x-hit"); }
      var h = c.querySelector(":scope > h3, :scope > .doc-page-head");
      if (h && b.tagName !== "TR") h.parentNode.removeChild(h);
      c.classList.remove("x-hit");
      return strip(c);
    }
    function label(id, t, b) {
      var m = /^(?:reg-)?((?:FND|EV|DEG|AD|SA|RQ)-\d+)$/.exec(id);
      if (m) return m[1];
      if (b.hasAttribute("data-kicker")) return b.getAttribute("data-kicker");     // an entry that names its kind
      if (b.classList.contains("doc-page")) {
        if (t.classList.contains("doc-sec")) return t.getAttribute("data-label").split(" ")[0];
        return "p." + (/-p(\d+)$/.exec(b.id) || ["", "?"])[1];
      }
      var h = b.querySelector("h3");
      var s = (h ? h.textContent : b.textContent).replace(/\s+/g, " ").trim();
      return s.length > 22 ? s.slice(0, 21) + "…" : s;
    }
    function title(id, t, b) {
      var s;
      if (b.classList.contains("doc-page")) {
        s = t.classList.contains("doc-sec") ? t.getAttribute("data-label")
          : b.querySelector(".doc-page-head span").textContent;
      } else if (b.tagName === "ARTICLE") {
        var f = b.querySelector("h3 .x-fid"), h3 = b.querySelector("h3");
        s = h3.textContent.slice(f ? f.textContent.length : 0);
      } else if (b.classList.contains("x-ev-entry") && b.querySelector(".x-q")) {
        s = b.querySelector(".x-q").textContent;                       // an evidence item: its excerpt
      } else {
        var h = b.querySelector("h3");
        s = h ? h.textContent : b.textContent;
      }
      s = s.replace(/\s+/g, " ").trim();
      return s.length > 140 ? s.slice(0, 138) + "…" : s;
    }
    function draw() {
      var id = stack[at], t = document.getElementById(id), b = block(t), c = copy(t, b);
      pbody.textContent = "";
      if (b.classList.contains("x-ev-entry")) {                        // its excerpt is the title: not twice
        var q = c.querySelector(":scope > .x-q");
        if (q) q.parentNode.removeChild(q);
      }
      pbody.appendChild(c);
      pkick.textContent = label(id, t, b);
      ptitle.textContent = title(id, t, b);
      pcrumb.textContent = "";
      for (var i = 0; i < stack.length; i++) {
        var ti = document.getElementById(stack[i]);
        if (i) pcrumb.appendChild(el("span", "x-crumb-sep", "›"));
        var cb = el("button", i === at ? "x-crumb cur" : "x-crumb", label(stack[i], ti, block(ti)));
        cb.type = "button"; cb.setAttribute("data-i", String(i));
        if (i === at) cb.setAttribute("aria-current", "location");
        pcrumb.appendChild(cb);
      }
      pcrumb.hidden = stack.length < 2;
      pprev.disabled = at <= 0;
      pnext.disabled = at >= stack.length - 1;
      var pdf = b.classList.contains("doc-page") ? b.querySelector(".x-pdf") : null;
      ppdf.hidden = !pdf;
      if (pdf) { ppdf.href = pdf.getAttribute("href"); ppdf.textContent = pdf.textContent; }
      if (pmore) {
        var more = opt.more(id);
        pmore.hidden = !more;
        if (more) { pmore.href = more.href; pmore.textContent = more.label; }
      }
      pbody.scrollTop = 0;
      var hit = c.querySelector(".x-hit");
      if (hit && b.classList.contains("doc-page")) pbody.scrollTop = Math.max(0, hit.offsetTop - pbody.clientHeight / 3);
    }
    function mark(a) {
      if (opener) opener.classList.remove("x-opener");
      opener = a && !a.closest(".x-pane") ? a : opener;
      if (opener) opener.classList.add("x-opener");
    }
    // Beside the pane: from 1280 px, while the pane is open the reading column ends left of it (its measure narrows,
    // and the class "x-beside" lets the page hide what the pane covers), so no line runs under the pane. The reflow
    // and the scroll that undoes it happen in one task, before any paint: the link the reader clicked keeps its exact
    // place on the screen, on open and on close. Below 1280 px there is no room, and the pane is an overlay.
    var col = box.querySelector(opt.column || ".wrap"), GAP = 24, WIDE = 1280, MEASURE = 440;
    function topOf(a) { return a && a.isConnected && a.getClientRects().length ? a.getBoundingClientRect().top : null; }
    function room(on) {
      if (!col) return;
      box.classList.remove("x-beside");
      col.style.maxWidth = "";
      if (!on || window.innerWidth < WIDE) return;
      box.classList.add("x-beside");
      var r = col.getBoundingClientRect(), w = pane.getBoundingClientRect().left - GAP - r.left;
      if (w >= r.width) return;                        // it already ends left of the pane: nothing to make room for
      if (w >= MEASURE) col.style.maxWidth = w + "px"; else box.classList.remove("x-beside");
    }
    function settle(a, top0) {                          // the link back where it was, to the pixel
      var top1 = top0 === null ? null : topOf(a);
      if (top1 !== null && top1 !== top0) window.scrollBy(0, top1 - top0);
    }
    function openPane(id, a) {
      if (!pane) { jump(id); return; }
      hide();
      var fresh = !paneOpen(), top0 = fresh ? topOf(a) : null;
      if (fresh || !a.closest(".x-pane")) { gen += 1; stack = [id]; at = 0; }
      else { stack = stack.slice(0, at + 1); stack.push(id); at += 1; }
      if (fresh) { save(); depth = 0; }
      depth += 1;
      if (hist) { try { history.pushState({ pane: at, stack: stack.slice(), gen: gen, d: depth }, ""); } catch (x) {} }
      mark(a);
      pane.hidden = false;
      root.classList.add("pane-open");
      draw();
      if (fresh) { room(true); settle(a, top0); }
      if (fresh || !a.closest(".x-pane")) ptitle.focus({ preventScroll: true });
    }
    function adopt(s) {
      // the same chain keeps the entries ahead of this one, so the pane's Forward still has somewhere to go
      var same = s.gen === gen && stack.length > s.pane && stack[s.pane] === s.stack[s.pane];
      if (!same) stack = s.stack.slice();
      at = s.pane; gen = s.gen; depth = s.d || 1;
      if (!paneOpen()) { pane.hidden = false; root.classList.add("pane-open"); room(true); }
      draw();
    }
    function closed() {
      var top0 = topOf(opener);
      pane.hidden = true;
      root.classList.remove("pane-open");
      room(false);
      settle(opener, top0);
      stack = []; at = -1; depth = 0;
      var o = opener;
      if (opener) opener.classList.remove("x-opener");
      opener = null;
      if (o) o.focus({ preventScroll: true });
    }
    function closePane() {
      if (!paneOpen()) return;
      var s = st();
      if (hist && typeof s.pane === "number" && depth > 0) history.go(-depth);   // its popstate closes the pane
      else { closed(); if (after) { var f = after; after = null; f(); } }
    }
    on(window, "scroll", function () { if (shown) { pop.hidden = true; shown = null; } }, { passive: true });
    on(window, "resize", function () {                 // a new width: the room beside the pane again, the link kept
      if (!paneOpen()) return;
      var top0 = topOf(opener);
      room(true);
      settle(opener, top0);
    });
    if (hist) route(); else landing();
    return { destroy: destroy };
  }
  window.sitXnav = xnav;
  if (document.documentElement.classList.contains("export-doc")) xnav(document.body, { history: true });
})();
