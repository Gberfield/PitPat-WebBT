(function(root, factory) {
    const createUI = factory();
    if (typeof module === 'object' && module.exports) module.exports = {createUI};
    else { root.PitPatUI = createUI(document, location); root.PitPatUI.init(); }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    return function createUI(doc, location, history = globalThis.history) {
        let resolveChoice = null;
        const dialog = doc.getElementById('deviceDialog');
        function finish(id) {
            dialog.close();
            const resolve = resolveChoice; resolveChoice = null;
            if (resolve) resolve(id);
        }
        doc.getElementById('cancelDeviceBtn').addEventListener('click', () => finish(null));
        dialog.addEventListener('cancel', event => { event.preventDefault(); finish(null); });
        return {
            init() {
                const tabs = [...doc.querySelectorAll('.mdl-layout__tab')];
                function activate(tab) {
                    for (const item of tabs) {
                        const active = item === tab;
                        item.setAttribute('aria-selected', String(active)); item.tabIndex = active ? 0 : -1;
                        item.classList.toggle('is-active', active);
                        const panel = doc.getElementById(item.getAttribute('href').slice(1));
                        panel.hidden = !active; panel.classList.toggle('is-active', active);
                    }
                }
                tabs.forEach((tab, index) => {
                    tab.setAttribute('role', 'tab');
                    tab.addEventListener('click', event => {
                        event.preventDefault(); activate(tab); tab.focus();
                        history?.replaceState(null, '', tab.getAttribute('href'));
                    });
                    tab.addEventListener('keydown', event => {
                        let next = index;
                        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
                        else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
                        else if (event.key === 'Home') next = 0;
                        else if (event.key === 'End') next = tabs.length - 1;
                        else return;
                        event.preventDefault(); activate(tabs[next]); tabs[next].focus();
                        history?.replaceState(null, '', tabs[next].getAttribute('href'));
                    });
                });
                if (tabs.length) activate(tabs.find(t => t.getAttribute('href') === location.hash) || tabs[0]);
            },
            chooseDevice(devices) {
                if (!devices.length) return Promise.resolve(null);
                if (resolveChoice) finish(null);
                const choices = doc.getElementById('deviceChoices'); choices.replaceChildren();
                for (const device of devices) {
                    const button = doc.createElement('button'); button.type = 'button'; button.textContent = device.name;
                    button.addEventListener('click', () => finish(device.id)); choices.appendChild(button);
                }
                return new Promise(resolve => { resolveChoice = resolve; dialog.showModal(); choices.children[0]?.focus(); });
            }
        };
    };
});
